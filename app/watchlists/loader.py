from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.config import PROJECT_ROOT, settings


logger = logging.getLogger(__name__)

GITHUB_DOMAIN_SECRET_TERMS = [
    ".env",
    "DB_PASSWORD",
    "API_KEY",
    "SECRET_KEY",
    "password",
    "token",
]


@dataclass(frozen=True)
class OrganizationProfile:
    name: str
    category: str = ""
    country: str = ""
    domains: list[str] = field(default_factory=list)
    email_patterns: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    brand_names: list[str] = field(default_factory=list)
    internal_project_names: list[str] = field(default_factory=list)
    github_queries: list[str] = field(default_factory=list)
    source_settings: dict[str, Any] = field(default_factory=dict)

    def watch_terms(self) -> list[str]:
        terms: list[str] = []
        for value in (
            *self.domains,
            *self.email_patterns,
            *self.keywords,
            *self.brand_names,
            *self.internal_project_names,
        ):
            normalized = value.strip()
            if normalized and normalized not in terms:
                terms.append(normalized)
        return terms


@dataclass(frozen=True)
class GlobalRiskQuery:
    query: str
    risk_category: str
    severity_hint: str
    notes: str = ""
    exclude: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GlobalRiskCategory:
    key: str
    name: str
    severity_hint: str
    description: str = ""
    queries: list[GlobalRiskQuery] = field(default_factory=list)


@dataclass(frozen=True)
class GitHubSearchSpec:
    query: str
    organization: str = ""
    risk_category: str = ""


def _organizations_dir() -> Path:
    configured = settings.WATCHLISTS_ORGANIZATIONS_DIR
    if isinstance(configured, Path):
        return configured
    if isinstance(configured, str):
        return Path(configured)
    return PROJECT_ROOT / "app" / "watchlists" / "organizations"


def _global_risks_path() -> Path:
    configured = settings.WATCHLISTS_GLOBAL_RISKS_PATH
    if isinstance(configured, Path):
        return configured
    if isinstance(configured, str):
        return Path(configured)
    return PROJECT_ROOT / "app" / "watchlists" / "global_risks.yml"


def _organizations_file() -> Path:
    configured = settings.WATCHLISTS_ORGANIZATIONS_FILE
    if isinstance(configured, Path):
        return configured
    if isinstance(configured, str):
        return Path(configured)
    return PROJECT_ROOT / "config" / "organizations_watchlist.yml"


def organization_watchlists_enabled() -> bool:
    """Return whether optional organization-specific correlation is enabled.

    The MVP is global-first: GitHub monitoring is driven by
    ``global_risks.yml``. Organization profiles are an opt-in extension for
    tagging/correlation, not a prerequisite for scanning.
    """

    return bool(getattr(settings, "ORGANIZATION_WATCHLISTS_ENABLED", False))


def _string_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _coerce_query_string(value: Any) -> str:
    """Join YAML split scalars into one GitHub search query string."""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, list):
        parts = [_coerce_query_string(item) for item in value]
        return " ".join(part for part in parts if part)
    if value is None:
        return ""
    return " ".join(str(value).split())


def _normalize_global_risk_query_entry(
    entry: Any,
    *,
    risk_category: str,
    severity_hint: str,
) -> GlobalRiskQuery | None:
    if isinstance(entry, str):
        query = _coerce_query_string(entry)
        return GlobalRiskQuery(
            query=query,
            risk_category=risk_category,
            severity_hint=severity_hint,
        ) if query else None

    if not isinstance(entry, dict):
        return None

    query = _coerce_query_string(entry.get("query"))
    if not query:
        return None

    notes = str(entry.get("notes", "")).strip()
    exclude = _string_list(entry.get("exclude"))

    return GlobalRiskQuery(
        query=query,
        risk_category=risk_category,
        severity_hint=severity_hint,
        notes=notes,
        exclude=exclude,
    )


def _parse_profile(data: dict[str, Any]) -> OrganizationProfile | None:
    name = str(data.get("name", "")).strip()
    if not name:
        return None

    def _list_field(key: str) -> list[str]:
        raw = data.get(key, [])
        if not isinstance(raw, list):
            return []
        return [str(item).strip() for item in raw if str(item).strip()]

    profile = OrganizationProfile(
        name=name,
        category=str(data.get("category", "")).strip(),
        country=str(data.get("country", "")).strip(),
        domains=_list_field("domains"),
        email_patterns=_list_field("email_patterns"),
        keywords=_list_field("keywords"),
        brand_names=_list_field("brand_names"),
        internal_project_names=_list_field("internal_project_names"),
        github_queries=_list_field("github_queries"),
        source_settings=data.get("source_settings") if isinstance(data.get("source_settings"), dict) else {},
    )
    if not profile.watch_terms() and not profile.github_queries:
        return None
    return profile


def _profiles_from_payload(payload: Any) -> list[OrganizationProfile]:
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("organizations"), list):
        raw_profiles = payload["organizations"]
    else:
        raw_profiles = [payload]

    profiles: list[OrganizationProfile] = []
    for raw_profile in raw_profiles:
        if not isinstance(raw_profile, dict):
            continue
        profile = _parse_profile(raw_profile)
        if profile is not None:
            profiles.append(profile)
    return profiles


def _parse_global_risk_category(key: str, data: dict[str, Any]) -> GlobalRiskCategory | None:
    if not key.strip() or not isinstance(data, dict):
        return None

    severity_hint = str(data.get("severity_hint", "medium")).strip().lower() or "medium"
    raw_queries = data.get("queries", [])
    if not isinstance(raw_queries, list):
        raw_queries = []

    queries: list[GlobalRiskQuery] = []
    for entry in raw_queries:
        normalized = _normalize_global_risk_query_entry(
            entry,
            risk_category=key.strip(),
            severity_hint=severity_hint,
        )
        if normalized is not None:
            queries.append(normalized)

    if not queries:
        return None

    return GlobalRiskCategory(
        key=key.strip(),
        name=str(data.get("name", key)).strip() or key.strip(),
        severity_hint=severity_hint,
        description=str(data.get("description", "")).strip(),
        queries=queries,
    )


def load_organizations(*, refresh: bool = False) -> list[OrganizationProfile]:
    global _cached_organizations
    if not organization_watchlists_enabled():
        _cached_organizations = []
        return []
    if not refresh and _cached_organizations is not None:
        return _cached_organizations

    profiles: list[OrganizationProfile] = []
    org_dir = _organizations_dir()
    if org_dir.is_dir():
        for path in sorted(org_dir.glob("*.yml")) + sorted(org_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                continue
            profiles.extend(_profiles_from_payload(data))

    config_file = _organizations_file()
    if config_file.is_file():
        try:
            data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            logger.warning("Failed to load organization watchlist from %s: %s", config_file, exc)
            data = None
        profiles.extend(_profiles_from_payload(data))

    deduped: list[OrganizationProfile] = []
    seen_names: set[str] = set()
    for profile in profiles:
        key = profile.name.casefold()
        if key in seen_names:
            continue
        seen_names.add(key)
        deduped.append(profile)
    profiles = deduped

    _cached_organizations = profiles
    return profiles


def load_global_risks(*, refresh: bool = False) -> list[GlobalRiskCategory]:
    global _cached_global_risks
    if not refresh and _cached_global_risks is not None:
        return _cached_global_risks

    categories: list[GlobalRiskCategory] = []
    path = _global_risks_path()
    if path.is_file():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            logger.warning("Failed to load global risk profile from %s: %s", path, exc)
            data = None

        if isinstance(data, dict):
            raw_categories = data.get("categories", {})
            if isinstance(raw_categories, dict):
                for key, category_data in raw_categories.items():
                    if not isinstance(category_data, dict):
                        continue
                    category = _parse_global_risk_category(str(key), category_data)
                    if category is not None:
                        categories.append(category)

    query_count = sum(len(category.queries) for category in categories)
    logger.info(
        "Loaded %s global risk queries across %s categories from %s.",
        query_count,
        len(categories),
        path,
    )

    _cached_global_risks = categories
    return categories


def _quote_query_value(value: str) -> str:
    escaped = value.strip().strip('"').replace('"', '\\"')
    return f'"{escaped}"'


def github_search_specs() -> list[GitHubSearchSpec]:
    """Return GitHub code search specs from global risk profiles by default.

    Organization-derived queries are appended only when
    ``ORGANIZATION_WATCHLISTS_ENABLED=true``. The scanner must remain useful
    without any organization watchlist.
    """
    specs: list[GitHubSearchSpec] = []
    seen: set[str] = set()

    def _append(
        query: str,
        *,
        organization: str = "",
        risk_category: str = "",
    ) -> None:
        normalized = query.strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        specs.append(
            GitHubSearchSpec(
                query=normalized,
                organization=organization.strip(),
                risk_category=risk_category.strip(),
            )
        )

    for category in load_global_risks():
        for risk_query in category.queries:
            _append(risk_query.query, risk_category=risk_query.risk_category)

    if organization_watchlists_enabled():
        for profile in load_organizations():
            for configured_query in profile.github_queries:
                _append(configured_query, organization=profile.name)

            for term in profile.watch_terms():
                _append(_quote_query_value(term), organization=profile.name)

            for domain in profile.domains:
                domain_query = _quote_query_value(domain)
                for secret_term in GITHUB_DOMAIN_SECRET_TERMS:
                    _append(
                        f"{domain_query} {_quote_query_value(secret_term)}",
                        organization=profile.name,
                    )

    for configured_query in settings.GITHUB_SEARCH_QUERIES:
        _append(configured_query)

    return specs


def github_queries_for_organizations() -> list[tuple[str, str]]:
    """Backward-compatible (query, organization) pairs for GitHub code search."""
    return [(spec.query, spec.organization) for spec in github_search_specs()]


_cached_organizations: list[OrganizationProfile] | None = None
_cached_global_risks: list[GlobalRiskCategory] | None = None
