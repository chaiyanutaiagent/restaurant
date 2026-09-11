from __future__ import annotations

import re
import unicodedata


BUSINESS_SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])$")
RESERVED_BUSINESS_SLUGS = frozenset(
    {
        "403",
        "accounting",
        "admin",
        "api",
        "billing",
        "branches",
        "central",
        "counter",
        "crm",
        "dashboard",
        "device",
        "devices",
        "erp",
        "etax",
        "forgot-password",
        "hr",
        "integrations",
        "kitchen",
        "logistics",
        "login",
        "menu",
        "order",
        "payable",
        "pickup",
        "platform",
        "pos",
        "privacy-support",
        "products",
        "purchase",
        "reports",
        "reset-password",
        "restaurant",
        "roles",
        "settings",
        "shift-history",
        "signup",
        "stock",
        "stock-count",
        "store",
        "transfer",
        "units",
        "uploads",
        "users",
        "verify-email",
    }
)


def normalize_business_slug(value: str) -> str:
    normalized = value.strip().lower()
    if (
        not BUSINESS_SLUG_PATTERN.fullmatch(normalized)
        or "--" in normalized
        or normalized in RESERVED_BUSINESS_SLUGS
    ):
        raise ValueError(
            "business_slug must be 3-63 lowercase letters, numbers, or single hyphens and must not be reserved"
        )
    return normalized


def suggest_business_slug(name: str, *, fallback_suffix: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    candidate = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:63].rstrip("-")
    if len(candidate) < 3 or candidate in RESERVED_BUSINESS_SLUGS:
        candidate = f"business-{fallback_suffix.lower()}"
    candidate = candidate[:63].rstrip("-")
    return normalize_business_slug(candidate)
