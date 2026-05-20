from __future__ import annotations

import re

from app.detection.extractors import ExtractedSecret, extract_secret_candidates
from app.detection.noise import is_example_path
from app.detection.policy import load_detection_policy
from app.detection.scoring import score_validated_detection
from app.detection.validators import validate_candidate
from app.processing.categories import (
    EXPOSURE_SIGNAL,
    INFORMATIONAL_MENTION,
    SECRET_EXPOSURE,
    STORABLE_CATEGORIES,
)
from app.watchlists.loader import load_organizations


EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
DOMAIN_RE = re.compile(
    r"(?<![@A-Za-z0-9_-])(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24}\b",
    re.IGNORECASE,
)
GITHUB_TOKEN_RE = re.compile(
    r"\b(?:gh[opsur]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{20,}_[A-Za-z0-9_]{20,})\b"
)
OPENAI_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b")
AWS_ACCESS_KEY_RE = re.compile(r"\bAKIA[A-Z0-9]{16}\b")
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
BEARER_TOKEN_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b", re.IGNORECASE)
API_KEY_ASSIGNMENT_RE = re.compile(
    r"\b(?:api[_-]?key|secret[_-]?key|client[_-]?secret|access[_-]?key)\b\s*[:=]\s*[\"']?[A-Za-z0-9._~+/=-]{12,}[\"']?",
    re.IGNORECASE,
)
TOKEN_ASSIGNMENT_RE = re.compile(
    r"\b(?:access[_-]?token|refresh[_-]?token|auth[_-]?token|token)\b\s*[:=]\s*[\"']?[A-Za-z0-9._~+/=-]{16,}[\"']?",
    re.IGNORECASE,
)
PASSWORD_ASSIGNMENT_RE = re.compile(
    r"\b(?:password|passwd|pwd|db_password|database_password)\b\s*[:=]\s*[\"']?[^\s,;\"']{8,}[\"']?",
    re.IGNORECASE,
)
DB_URI_RE = re.compile(
    r"\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|mariadb)://[^\s'\"<>]+",
    re.IGNORECASE,
)
SENSITIVE_KEYWORDS = [
    "password",
    "passwd",
    "pwd",
    "secret",
    "api_key",
    "token",
    "db_password",
]
SECRETISH_KEY_RE = re.compile(
    r"(api[_-]?key|secret|token|password|passwd|pwd|credential|private[_-]?key|client[_-]?secret|database_url|db_url|aws_)",
    re.IGNORECASE,
)
PUBLIC_CONTACT_EMAIL_PREFIXES = (
    "info",
    "contact",
    "hello",
    "support",
    "office",
    "sales",
    "noreply",
    "no-reply",
    "mail",
    "webmaster",
)
EXPOSURE_CONTEXT_KEYWORDS = [
    "dump",
    "leak",
    "breach",
    "credentials",
    "database export",
    "users table",
    "admin password",
    ".env",
    "db_password",
    "api_key",
    "secret_key",
    "private key",
]
SUSPICIOUS_PATH_MARKERS = (
    ".env",
    "/config",
    "config/",
    "backup",
    "dump",
    ".sql",
    "credentials",
    "secrets",
    ".pem",
    ".key",
)
PHONE_RE = re.compile(
    r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b"
)
PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----", re.IGNORECASE)
LOOSE_EXPOSURE_PATTERNS = (
    re.compile(r"\bpassword\s*=", re.IGNORECASE),
    re.compile(r"\bdb_password\b", re.IGNORECASE),
    re.compile(r"\bapi_key\b", re.IGNORECASE),
    re.compile(r"\bsecret_key\b", re.IGNORECASE),
    re.compile(r"\btoken\s*=", re.IGNORECASE),
    re.compile(r"\bbearer\s+", re.IGNORECASE),
)
VALID_TLDS = {
    "ac",
    "ad",
    "ae",
    "af",
    "ag",
    "ai",
    "al",
    "am",
    "ao",
    "app",
    "aq",
    "ar",
    "as",
    "at",
    "au",
    "aw",
    "ax",
    "az",
    "ba",
    "bb",
    "bd",
    "be",
    "bf",
    "bg",
    "bh",
    "bi",
    "biz",
    "bj",
    "bm",
    "bn",
    "bo",
    "br",
    "bs",
    "bt",
    "bw",
    "by",
    "bz",
    "ca",
    "cat",
    "cc",
    "cd",
    "cf",
    "cg",
    "ch",
    "ci",
    "cl",
    "cm",
    "cn",
    "co",
    "cloud",
    "com",
    "cr",
    "cu",
    "cv",
    "cw",
    "cy",
    "cz",
    "de",
    "dev",
    "dj",
    "dk",
    "dm",
    "do",
    "dz",
    "ec",
    "edu",
    "ee",
    "eg",
    "er",
    "es",
    "et",
    "eu",
    "fi",
    "fj",
    "fm",
    "fr",
    "ga",
    "gd",
    "ge",
    "gg",
    "gh",
    "gi",
    "gl",
    "gm",
    "gov",
    "gp",
    "gq",
    "gr",
    "gs",
    "gt",
    "gu",
    "gw",
    "gy",
    "hk",
    "hm",
    "hn",
    "hr",
    "ht",
    "hu",
    "id",
    "ie",
    "il",
    "im",
    "in",
    "info",
    "int",
    "io",
    "iq",
    "ir",
    "is",
    "it",
    "je",
    "jm",
    "jo",
    "jobs",
    "jp",
    "ke",
    "kg",
    "kh",
    "ki",
    "km",
    "kn",
    "kp",
    "kr",
    "kw",
    "ky",
    "kz",
    "la",
    "lb",
    "lc",
    "li",
    "lk",
    "lr",
    "ls",
    "lt",
    "lu",
    "lv",
    "ly",
    "ma",
    "mc",
    "md",
    "me",
    "mg",
    "mil",
    "mk",
    "ml",
    "mm",
    "mn",
    "mo",
    "mobi",
    "mp",
    "mq",
    "mr",
    "ms",
    "mt",
    "mu",
    "museum",
    "mv",
    "mw",
    "mx",
    "my",
    "mz",
    "na",
    "name",
    "nc",
    "ne",
    "net",
    "nf",
    "ng",
    "ni",
    "nl",
    "no",
    "np",
    "nr",
    "nu",
    "nz",
    "om",
    "org",
    "pa",
    "pe",
    "pf",
    "pg",
    "ph",
    "pk",
    "pl",
    "pm",
    "pn",
    "pr",
    "pro",
    "ps",
    "pt",
    "pw",
    "py",
    "qa",
    "re",
    "ro",
    "rs",
    "ru",
    "rw",
    "sa",
    "sb",
    "sc",
    "sd",
    "se",
    "sg",
    "sh",
    "si",
    "sk",
    "sl",
    "sm",
    "sn",
    "so",
    "sr",
    "st",
    "su",
    "sv",
    "sx",
    "sy",
    "sz",
    "tc",
    "td",
    "tel",
    "tech",
    "tf",
    "tg",
    "th",
    "tj",
    "tk",
    "tl",
    "tm",
    "tn",
    "to",
    "tr",
    "travel",
    "tt",
    "tv",
    "tw",
    "tz",
    "ua",
    "ug",
    "uk",
    "us",
    "uy",
    "uz",
    "va",
    "vc",
    "ve",
    "vg",
    "vn",
    "vu",
    "wf",
    "ws",
    "xyz",
    "xn--p1ai",
    "ye",
    "yt",
    "za",
    "zm",
    "zw",
}
CODE_FILE_EXTENSIONS = {
    "cjs",
    "css",
    "jsx",
    "js",
    "json",
    "mjs",
    "php",
    "scss",
    "ts",
    "tsx",
    "yaml",
    "yml",
}


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _valid_domain(candidate: str) -> bool:
    labels = candidate.lower().rstrip(".").split(".")
    if len(labels) < 2:
        return False

    tld = labels[-1]
    if tld in CODE_FILE_EXTENSIONS:
        return False
    if tld not in VALID_TLDS:
        return False
    return all(label and not label.startswith("-") and not label.endswith("-") for label in labels)


def _extract_domains(text: str) -> list[str]:
    return _unique([match.group(0) for match in DOMAIN_RE.finditer(text) if _valid_domain(match.group(0))])


def _pattern_matches(text: str, patterns: tuple[re.Pattern[str], ...]) -> list[str]:
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(match.group(0) for match in pattern.finditer(text))
    return _unique(matches)


def _is_public_contact_email(email: str) -> bool:
    local, _, domain = email.lower().partition("@")
    if not local or not domain:
        return False
    return local in PUBLIC_CONTACT_EMAIL_PREFIXES


def _find_suspicious_paths(text: str) -> list[str]:
    lowered = text.lower()
    return _unique([marker for marker in SUSPICIOUS_PATH_MARKERS if marker in lowered])


def _find_exposure_keywords(text: str) -> list[str]:
    lowered = text.lower()
    return _unique(
        [keyword for keyword in EXPOSURE_CONTEXT_KEYWORDS if keyword.lower() in lowered]
    )


def _append_content_evidence(evidence: list[str], label: str) -> None:
    if label and label not in evidence:
        evidence.append(label)


def extract_content_evidence(content: str, file_path: str = "") -> list[str]:
    """Return evidence labels found in file content (not search query context)."""
    evidence: list[str] = []

    if LOOSE_EXPOSURE_PATTERNS[0].search(content):
        _append_content_evidence(evidence, "password=")
    if re.search(r"\bdb_password\b", content, re.IGNORECASE):
        _append_content_evidence(evidence, "DB_PASSWORD")
    if API_KEY_ASSIGNMENT_RE.search(content) or re.search(
        r"\bapi_key\b\s*=", content, re.IGNORECASE
    ):
        _append_content_evidence(evidence, "API_KEY")
    if re.search(r"\bsecret_key\b", content, re.IGNORECASE):
        _append_content_evidence(evidence, "SECRET_KEY")
    if TOKEN_ASSIGNMENT_RE.search(content) or re.search(r"\btoken\s*=", content, re.IGNORECASE):
        _append_content_evidence(evidence, "token=")
    if JWT_RE.search(content):
        _append_content_evidence(evidence, "JWT")
    if BEARER_TOKEN_RE.search(content):
        _append_content_evidence(evidence, "Bearer token")
    if GITHUB_TOKEN_RE.search(content):
        _append_content_evidence(evidence, "GITHUB_TOKEN")
    if OPENAI_KEY_RE.search(content):
        _append_content_evidence(evidence, "OPENAI_KEY")
    if AWS_ACCESS_KEY_RE.search(content):
        _append_content_evidence(evidence, "AWS_ACCESS_KEY")
    if PRIVATE_KEY_RE.search(content):
        _append_content_evidence(evidence, "PRIVATE_KEY")
    if PASSWORD_ASSIGNMENT_RE.search(content):
        _append_content_evidence(evidence, "password_assignment")

    for uri in DB_URI_RE.findall(content):
        lowered = uri.lower()
        if lowered.startswith("mongodb"):
            _append_content_evidence(evidence, "mongodb://")
        elif lowered.startswith("postgres"):
            _append_content_evidence(evidence, "postgres://")
        elif lowered.startswith("mysql"):
            _append_content_evidence(evidence, "mysql://")
        elif lowered.startswith("redis"):
            _append_content_evidence(evidence, "redis://")
        else:
            _append_content_evidence(evidence, "database_uri")

    path_lower = file_path.lower()
    for marker in SUSPICIOUS_PATH_MARKERS:
        if path_lower and marker in path_lower:
            _append_content_evidence(evidence, f"suspicious_path:{marker}")

    return evidence


def _has_confirmed_secrets(indicators: dict[str, list[str] | str]) -> bool:
    try:
        return int(indicators.get("validated_secrets_count") or 0) > 0
    except (TypeError, ValueError):
        return False


def _has_exposure_evidence(text: str, indicators: dict[str, list[str] | str]) -> bool:
    if _find_suspicious_paths(text):
        return True
    if _find_exposure_keywords(text):
        return True
    if PRIVATE_KEY_RE.search(text):
        return True
    if any(pattern.search(text) for pattern in LOOSE_EXPOSURE_PATTERNS):
        return True
    return False


def classify_detection_category(
    text: str, indicators: dict[str, list[str] | str]
) -> str:
    if _has_confirmed_secrets(indicators):
        return SECRET_EXPOSURE
    if _has_exposure_evidence(text, indicators):
        return EXPOSURE_SIGNAL
    return INFORMATIONAL_MENTION


def classify_detection_category_from_content(
    content: str,
    file_path: str,
    indicators: dict[str, list[str] | str],
) -> str:
    """Classify using file content and path only — not search query context."""
    content_evidence = extract_content_evidence(content, file_path)
    indicators["content_evidence"] = content_evidence

    if _has_confirmed_secrets(indicators):
        return SECRET_EXPOSURE
    if content_evidence:
        return EXPOSURE_SIGNAL
    return INFORMATIONAL_MENTION


def should_store_detection(indicators: dict[str, list[str] | str]) -> bool:
    final_decision = str(indicators.get("final_decision") or "")
    if final_decision == "ignore":
        return False
    if final_decision == "low_signal":
        return load_detection_policy().index_low_signals
    return str(indicators.get("detection_category", INFORMATIONAL_MENTION)) in STORABLE_CATEGORIES


def _candidate_is_secretish(candidate: ExtractedSecret) -> bool:
    if candidate.source != "assignment":
        return True
    if SECRETISH_KEY_RE.search(candidate.key):
        return True
    if DB_URI_RE.search(candidate.value):
        return True
    if PRIVATE_KEY_RE.search(candidate.value):
        return True
    if GITHUB_TOKEN_RE.search(candidate.value) or AWS_ACCESS_KEY_RE.search(candidate.value):
        return True
    if JWT_RE.search(candidate.value) or OPENAI_KEY_RE.search(candidate.value):
        return True
    return False


def _validation_label(candidate: ExtractedSecret, validation: dict[str, bool | str]) -> str:
    secret_type = str(validation.get("secret_type") or "unknown")
    reason = str(validation.get("reason") or "")
    return f"line {candidate.line_number} {candidate.key}: {secret_type} - {reason}"


def _apply_detection_pipeline(
    text: str,
    file_path: str,
    indicators: dict[str, list[str] | str | bool | int],
) -> None:
    policy = load_detection_policy()
    example_path, example_reason = is_example_path(file_path, policy)
    candidates = extract_secret_candidates(text)

    secretish_candidates = [candidate for candidate in candidates if _candidate_is_secretish(candidate)]
    validations: list[dict[str, bool | str]] = []
    placeholder_count = 0
    rejected_unknown_format = 0
    validation_reasons: list[str] = []
    secret_types: list[str] = []
    seen_valid_values: set[str] = set()

    for candidate in secretish_candidates:
        validation = validate_candidate(candidate)
        if validation.get("is_valid_candidate"):
            if candidate.value in seen_valid_values:
                continue
            seen_valid_values.add(candidate.value)
            validations.append(validation)
            secret_type = str(validation.get("secret_type") or "unknown")
            if secret_type not in secret_types:
                secret_types.append(secret_type)
            validation_reasons.append(_validation_label(candidate, validation))
            continue

        if str(validation.get("secret_type") or "") == "placeholder":
            placeholder_count += 1
        elif str(validation.get("secret_type") or "") == "unknown":
            rejected_unknown_format += 1
        validation_reasons.append(_validation_label(candidate, validation))

    decision = score_validated_detection(
        file_path=file_path,
        is_example_path=example_path,
        extracted_count=len(secretish_candidates),
        placeholder_count=placeholder_count,
        validations=validations,
        has_sensitive_keywords=bool(indicators.get("keywords")),
        has_suspicious_path=bool(indicators.get("suspicious_paths")) or example_path,
        has_domains=bool(indicators.get("domains")),
        has_watchlist=bool(indicators.get("matched_watchlist")),
        policy=policy,
    )

    indicators["is_example_path"] = example_path
    indicators["example_path_reason"] = example_reason
    indicators["is_noise"] = decision.is_noise
    indicators["noise_reason"] = decision.noise_reason
    indicators["extracted_secrets_count"] = len(secretish_candidates)
    indicators["validated_secrets_count"] = len(validations)
    indicators["placeholder_count"] = placeholder_count
    indicators["rejected_unknown_format"] = rejected_unknown_format
    indicators["secret_types"] = secret_types
    indicators["validation_reasons"] = validation_reasons
    indicators["final_decision"] = decision.final_decision
    indicators["triage_status"] = "new"
    indicators["confidence_score"] = decision.confidence_score
    indicators["risk_score"] = decision.risk_score
    indicators["severity"] = decision.severity
    indicators["confidence"] = decision.confidence


def _match_watchlist(text: str) -> tuple[list[str], str]:
    lowered = text.lower()
    matched_terms: list[str] = []
    matched_organizations: list[str] = []

    for profile in load_organizations():
        profile_matches = [term for term in profile.watch_terms() if term.lower() in lowered]
        if profile_matches:
            matched_organizations.append(profile.name)
            matched_terms.extend(profile_matches)

    organization = matched_organizations[0] if len(matched_organizations) == 1 else ""
    return _unique(matched_terms), organization


def detect_indicators(
    text: str,
    organization_hint: str | None = None,
    *,
    file_path: str = "",
    search_query_context: str = "",
    risk_category_hint: str | None = None,
    content_only: bool = False,
) -> dict[str, list[str] | str]:
    lowered = text.lower()
    matched_watchlist, matched_organization = _match_watchlist(text)
    organization = (organization_hint or "").strip() or matched_organization
    risk_category = (risk_category_hint or "").strip()

    keywords = [
        keyword
        for keyword in SENSITIVE_KEYWORDS
        if re.search(rf"\b{re.escape(keyword)}\b", lowered, flags=re.IGNORECASE)
    ]

    emails = _unique(EMAIL_RE.findall(text))
    path_for_analysis = file_path if content_only else text
    suspicious_paths = _find_suspicious_paths(path_for_analysis)
    exposure_keywords = _find_exposure_keywords(text)
    phones = _unique(PHONE_RE.findall(text))

    indicators: dict[str, list[str] | str | bool] = {
        "emails": emails,
        "domains": _extract_domains(text),
        "secrets": _pattern_matches(
            text,
            (
                GITHUB_TOKEN_RE,
                OPENAI_KEY_RE,
                AWS_ACCESS_KEY_RE,
                JWT_RE,
                BEARER_TOKEN_RE,
                API_KEY_ASSIGNMENT_RE,
                TOKEN_ASSIGNMENT_RE,
            ),
        ),
        "db_uris": _unique(DB_URI_RE.findall(text)),
        "passwords": _pattern_matches(text, (PASSWORD_ASSIGNMENT_RE,)),
        "keywords": _unique(keywords),
        "matched_watchlist": matched_watchlist,
        "organization": organization,
        "risk_category": risk_category,
        "suspicious_paths": suspicious_paths,
        "exposure_keywords": exposure_keywords,
        "phones": phones,
        "public_contact_emails": [email for email in emails if _is_public_contact_email(email)],
        "search_query_context": search_query_context,
        "content_evidence": [],
        "evidence_lines": [],
        "evidence_line_numbers": [],
        "evidence_excerpt": "",
    }

    _apply_detection_pipeline(text, file_path, indicators)

    from app.processing.evidence import extract_line_evidence

    line_evidence = extract_line_evidence(text)
    indicators["evidence_lines"] = line_evidence["evidence_lines"]
    indicators["evidence_line_numbers"] = line_evidence["evidence_line_numbers"]
    indicators["evidence_excerpt"] = line_evidence["evidence_excerpt"]

    if content_only:
        category = classify_detection_category_from_content(text, file_path, indicators)
    else:
        indicators["content_evidence"] = extract_content_evidence(text, file_path)
        category = classify_detection_category(text, indicators)

    indicators["detection_category"] = category
    return indicators
