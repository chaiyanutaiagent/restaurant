"""Exact test-access origins shared by startup and request-time guards.

Adding a hostname is a reviewed code change, not a suffix or wildcard match.
Only QA persona mode may use loopback origins; bypass and Store superadmin may not.
"""
from __future__ import annotations

import re

APPROVED_UAT_HOSTS = frozenset({
    "uat-pos.foodchainservice.com",
    "uat-app.foodchainservice.com",
    "uat-restaurant.foodchainservice.com",
    "uat-retail.foodchainservice.com",
    "uat-takeaway.foodchainservice.com",
})


def resolve_uat_public_host(public_base_url: str) -> str:
    # Match the whole origin rather than extracting a hostname from an arbitrary
    # URL. Reject userinfo, ports (including :443), paths, query/fragment, controls
    # and trailing-dot/suffix-confusion spellings. A root slash is conventional.
    normalized = public_base_url.lower()
    for host in APPROVED_UAT_HOSTS:
        if normalized in {f"https://{host}", f"https://{host}/"}:
            return host
    raise ValueError("Test access requires an exact approved HTTPS Foodchainservice UAT origin")


def resolve_qa_access_authority(public_base_url: str) -> str:
    try:
        return resolve_uat_public_host(public_base_url)
    except ValueError:
        pass
    match = re.fullmatch(
        r"https?://(?P<host>localhost|127\.0\.0\.1)(?::(?P<port>[0-9]{1,5}))?/?",
        public_base_url,
        flags=re.IGNORECASE | re.ASCII,
    )
    if match:
        port = match.group("port")
        if port is None or (1 <= int(port) <= 65535 and str(int(port)) == port):
            return match.group("host").lower() + (f":{port}" if port else "")
    raise ValueError("QA access requires an approved UAT origin or explicit HTTP(S) loopback origin")
