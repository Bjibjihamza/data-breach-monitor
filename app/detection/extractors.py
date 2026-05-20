from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Iterable

from app.detection.token_patterns import (
    BARE_TOKEN_SCAN_RE,
    DOCKER_ENV_ARG_RE,
    PLIST_STRING_RE,
    YAML_KV_RE,
)


@dataclass(frozen=True)
class ExtractedSecret:
    key: str
    value: str
    line_number: int
    context: str
    raw: str
    source: str = "assignment"


ASSIGNMENT_RE = re.compile(
    r"""^\s*(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_.-]{1,100})\s*(?P<op>=|:)\s*(?P<value>.*?)\s*(?:[,;])?\s*$"""
)
JSON_ASSIGNMENT_RE = re.compile(
    r"""^\s*["'](?P<key>[^"']{1,100})["']\s*:\s*(?P<value>.*?)\s*,?\s*$"""
)
INLINE_ASSIGNMENT_RE = re.compile(
    r"""\b(?P<key>[A-Za-z_][A-Za-z0-9_.-]{1,100})\s*(?:=|:)\s*(?:"(?P<double>[^"]*)"|'(?P<single>[^']*)'|(?P<bare>[^\s,;]+))"""
)
PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]+)?PRIVATE KEY-----.*?-----END (?:[A-Z0-9 ]+)?PRIVATE KEY-----",
    re.IGNORECASE | re.DOTALL,
)
PRIVATE_KEY_BEGIN_RE = re.compile(r"-----BEGIN (?:[A-Z0-9 ]+)?PRIVATE KEY-----", re.IGNORECASE)
DATABASE_URL_RE = re.compile(
    r"\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|mariadb)://[^\s'\"<>]+",
    re.IGNORECASE,
)


def _line_number_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _context(lines: list[str], line_number: int, window: int = 1) -> str:
    start = max(0, line_number - 1 - window)
    end = min(len(lines), line_number + window)
    return "\n".join(lines[start:end]).strip()


def _strip_inline_comment(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""
    if cleaned[0] in {"'", '"'}:
        quote = cleaned[0]
        for index in range(1, len(cleaned)):
            if cleaned[index] == quote and cleaned[index - 1] != "\\":
                return cleaned[1:index]
        return cleaned[1:]
    return re.split(r"\s+#", cleaned, maxsplit=1)[0].strip().strip(",")


def _decode_k8s_value(raw_value: str) -> str:
    cleaned = raw_value.strip().strip('"').strip("'")
    if not cleaned or " " in cleaned:
        return cleaned
    try:
        decoded = base64.b64decode(cleaned, validate=True).decode("utf-8")
        if decoded:
            return decoded
    except (ValueError, UnicodeDecodeError):
        pass
    return cleaned


def extract_key_values(text: str) -> list[ExtractedSecret]:
    lines = text.splitlines()
    extracted: list[ExtractedSecret] = []
    seen: set[tuple[str, str, int]] = set()
    in_k8s_block = False
    k8s_block_indent = 0
    k8s_block_type = ""

    def append_candidate(
        key: str,
        value: str,
        line_number: int,
        raw: str,
        *,
        source: str = "assignment",
    ) -> None:
        unique_key = (key.lower(), value, line_number)
        if unique_key in seen:
            return
        seen.add(unique_key)
        extracted.append(
            ExtractedSecret(
                key=key,
                value=value,
                line_number=line_number,
                context=_context(lines, line_number),
                raw=raw.rstrip(),
                source=source,
            )
        )

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue

        lowered = stripped.lower()
        if lowered.startswith("stringdata:") or (lowered.startswith("data:") and not lowered.startswith("database")):
            in_k8s_block = True
            k8s_block_type = "data" if lowered.startswith("data:") else "stringdata"
            k8s_block_indent = len(line) - len(line.lstrip())
            continue
        if in_k8s_block:
            indent = len(line) - len(line.lstrip())
            if stripped and indent <= k8s_block_indent and not stripped.startswith("-"):
                in_k8s_block = False
                k8s_block_type = ""
            else:
                yaml_match = YAML_KV_RE.match(line)
                if yaml_match:
                    key = yaml_match.group("key").strip()
                    raw_value = _strip_inline_comment(yaml_match.group("value"))
                    value = _decode_k8s_value(raw_value) if k8s_block_type == "data" else raw_value
                    append_candidate(key, value, line_number, line, source="kubernetes_secret")
                continue

        docker_match = DOCKER_ENV_ARG_RE.match(line)
        if docker_match:
            key = docker_match.group("key").strip()
            value = _strip_inline_comment(docker_match.group("value"))
            append_candidate(key, value, line_number, line, source="dockerfile_env")
            continue

        match = JSON_ASSIGNMENT_RE.match(line) or ASSIGNMENT_RE.match(line)
        if not match:
            for inline_match in INLINE_ASSIGNMENT_RE.finditer(line):
                value = (
                    inline_match.group("double")
                    if inline_match.group("double") is not None
                    else inline_match.group("single")
                    if inline_match.group("single") is not None
                    else inline_match.group("bare") or ""
                )
                source = "cicd_env" if any(
                    marker in (line.lower())
                    for marker in (".github/workflows", "gitlab-ci", "circle", "azure-pipelines")
                ) else "assignment"
                append_candidate(
                    inline_match.group("key").strip(),
                    value.strip(),
                    line_number,
                    inline_match.group(0),
                    source=source,
                )
            continue

        key = match.group("key").strip().strip('"').strip("'")
        value = _strip_inline_comment(match.group("value"))
        source = "assignment"
        if any(token in lowered for token in ("env:", "secrets.", "${{ secrets")):
            source = "cicd_env"
        append_candidate(key, value, line_number, line, source=source)

    return extracted


def _private_key_candidates(text: str) -> Iterable[ExtractedSecret]:
    for match in PRIVATE_KEY_BLOCK_RE.finditer(text):
        line_number = _line_number_for_offset(text, match.start())
        lines = text.splitlines()
        yield ExtractedSecret(
            key="PRIVATE_KEY",
            value=match.group(0),
            line_number=line_number,
            context=_context(lines, line_number),
            raw=match.group(0).splitlines()[0],
            source="private_key",
        )

    if PRIVATE_KEY_BLOCK_RE.search(text):
        return

    for match in PRIVATE_KEY_BEGIN_RE.finditer(text):
        line_number = _line_number_for_offset(text, match.start())
        lines = text.splitlines()
        yield ExtractedSecret(
            key="PRIVATE_KEY",
            value=match.group(0),
            line_number=line_number,
            context=_context(lines, line_number),
            raw=match.group(0),
            source="private_key",
        )


def _bare_token_candidates(text: str) -> Iterable[ExtractedSecret]:
    lines = text.splitlines()
    for match in BARE_TOKEN_SCAN_RE.finditer(text):
        line_number = _line_number_for_offset(text, match.start())
        yield ExtractedSecret(
            key="TOKEN",
            value=match.group(0),
            line_number=line_number,
            context=_context(lines, line_number),
            raw=match.group(0),
            source="bare_token",
        )


def _database_url_candidates(text: str) -> Iterable[ExtractedSecret]:
    lines = text.splitlines()
    for match in DATABASE_URL_RE.finditer(text):
        line_number = _line_number_for_offset(text, match.start())
        yield ExtractedSecret(
            key="DATABASE_URL",
            value=match.group(0),
            line_number=line_number,
            context=_context(lines, line_number),
            raw=match.group(0),
            source="database_url",
        )


def _plist_candidates(text: str) -> Iterable[ExtractedSecret]:
    lines = text.splitlines()
    for match in PLIST_STRING_RE.finditer(text):
        line_number = _line_number_for_offset(text, match.start())
        yield ExtractedSecret(
            key=match.group("key").strip(),
            value=match.group("value").strip(),
            line_number=line_number,
            context=_context(lines, line_number),
            raw=match.group(0),
            source="assignment",
        )


def extract_secret_candidates(text: str) -> list[ExtractedSecret]:
    candidates = list(extract_key_values(text))
    candidates.extend(_private_key_candidates(text))
    candidates.extend(_database_url_candidates(text))
    candidates.extend(_bare_token_candidates(text))
    candidates.extend(_plist_candidates(text))

    unique: dict[tuple[str, str, int], ExtractedSecret] = {}
    for candidate in candidates:
        key = (candidate.key.lower(), candidate.value, candidate.line_number)
        unique.setdefault(key, candidate)
    return list(unique.values())
