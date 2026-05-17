from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


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
BARE_PROVIDER_TOKEN_RE = re.compile(
    r"\b(?:gh[oprsu]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{20,}_[A-Za-z0-9_]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|sk_live_[A-Za-z0-9]{16,}|AKIA[A-Z0-9]{16}|ASIA[A-Z0-9]{16}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b"
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


def extract_key_values(text: str) -> list[ExtractedSecret]:
    lines = text.splitlines()
    extracted: list[ExtractedSecret] = []
    seen: set[tuple[str, str, int]] = set()

    def append_candidate(key: str, value: str, line_number: int, raw: str) -> None:
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
                source="assignment",
            )
        )

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
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
                append_candidate(
                    inline_match.group("key").strip(),
                    value.strip(),
                    line_number,
                    inline_match.group(0),
                )
            continue

        key = match.group("key").strip().strip('"').strip("'")
        value = _strip_inline_comment(match.group("value"))
        append_candidate(key, value, line_number, line)

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
    for match in BARE_PROVIDER_TOKEN_RE.finditer(text):
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


def extract_secret_candidates(text: str) -> list[ExtractedSecret]:
    candidates = list(extract_key_values(text))
    candidates.extend(_private_key_candidates(text))
    candidates.extend(_database_url_candidates(text))
    candidates.extend(_bare_token_candidates(text))

    unique: dict[tuple[str, str, int], ExtractedSecret] = {}
    for candidate in candidates:
        key = (candidate.key.lower(), candidate.value, candidate.line_number)
        unique.setdefault(key, candidate)
    return list(unique.values())
