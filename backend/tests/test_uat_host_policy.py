from __future__ import annotations

from types import SimpleNamespace as NS
import unittest
import uuid
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

from fastapi import HTTPException, Response
from starlette.requests import Request

from app.config import (
    resolve_uat_auth_bypass_hosts,
    validate_company_supply_chain_write_activation_config,
    validate_physical_uat_evidence_config,
    validate_pos_offline_mode_config,
    validate_qa_access_mode_config,
    validate_takeaway_write_activation_config,
    validate_uat_auth_bypass_config,
    validate_uat_superadmin_access_config,
)
from app.routers.auth import _qa_access_guard, uat_auto_login
from app.routers.platform import _platform_qa_access_guard, uat_platform_auto_login
from app.services.mobile_store_policy import uat_superadmin_store_access
from app.utils.uat_host_policy import APPROVED_UAT_HOSTS, resolve_qa_access_authority, resolve_uat_public_host

HOST = "uat-pos.foodchainservice.com"
ORIGIN = f"https://{HOST}"
COMPANY = uuid.uuid4()
BAD_ORIGINS = (
    "https://uat-attacker.example", "https://uat-pos.foodchainservice.com.attacker.example",
    "https://uat-pos.evilfoodchainservice.com", "https://uat-unapproved.foodchainservice.com",
    "https://*.foodchainservice.com", "https://uat-*.foodchainservice.com",
    ORIGIN + ":443", ORIGIN + ":8443", ORIGIN + ":", ORIGIN + ":not-a-port",
    "https://user:password@" + HOST, "https://@" + HOST,
    "https://" + HOST + "@attacker.example", ORIGIN + "/admin", ORIGIN + "//",
    ORIGIN + "/../", ORIGIN + "/%2e%2e/", ORIGIN + "?redirect=elsewhere",
    ORIGIN + "?", ORIGIN + "#fragment", ORIGIN + "#", ORIGIN + ".",
    "http://" + HOST, "//" + HOST, "https://[invalid", "", " " + ORIGIN,
    ORIGIN + "\n", "https://uat-\tpos.foodchainservice.com",
)
BAD_HEADERS = (
    "uat-attacker.example", HOST + ".evil.example", "uat-unapproved.foodchainservice.com",
    "*.foodchainservice.com", HOST + ":443", HOST + ":8443", "user@" + HOST,
    HOST + "/admin", HOST + "?query", HOST + "#fragment", HOST + ".", HOST + ", evil.example",
    " " + HOST, "",
)


def request(host: str) -> Request:
    return Request({"type": "http", "method": "POST", "path": "/",
                    "headers": [(b"host", host.encode())]})


def runtime(base_url=ORIGIN):
    return NS(environment="development", saas_public_base_url=base_url,
              uat_auth_bypass_enabled=True, uat_auth_bypass_company_id=COMPANY,
              uat_auth_bypass_username="fixture-admin", uat_platform_auth_bypass_username="fixture-platform",
              uat_auth_bypass_hosts=[], qa_access_mode_enabled=True, qa_access_key="k" * 32,
              uat_superadmin_all_logins_enabled=True, uat_superadmin_company_id=COMPANY,
              uat_superadmin_username="fixture-admin")


def startup_checks(url):
    base = dict(environment="development", public_base_url=url)
    return (
        lambda: validate_uat_auth_bypass_config(**base, enabled=True, company_id=COMPANY,
            username="fixture-admin", platform_username="fixture-platform"),
        lambda: validate_uat_superadmin_access_config(**base, enabled=True, company_id=COMPANY, username="fixture-admin"),
        lambda: validate_qa_access_mode_config(**base, enabled=True, company_id=COMPANY, access_key="k" * 32,
            personas={"owner": "fixture-owner"}, platform_personas={"admin": "fixture-platform"}),
        lambda: validate_takeaway_write_activation_config(**base, legacy_uat_enabled=False, mode="uat",
            feature_enabled=True, company_allowlist="", brand_allowlist="", branch_allowlist="", approval_reference=None),
        lambda: validate_company_supply_chain_write_activation_config(**base, kitchen_writes_enabled=True, distribution_writes_enabled=True),
        lambda: validate_pos_offline_mode_config(**base, enabled=True, company_allowlist=str(COMPANY), branch_allowlist=str(uuid.uuid4())),
        lambda: validate_physical_uat_evidence_config(**base, enabled=True),
    )


class UatOriginStartupTests(unittest.TestCase):
    def test_all_approved_origins_are_accepted_by_every_uat_startup_gate(self):
        for host in APPROVED_UAT_HOSTS:
            for url in (f"https://{host}", f"https://{host}/", f"HTTPS://{host.upper()}"):
                with self.subTest(url=url):
                    self.assertEqual(resolve_uat_public_host(url), host)
                    for validate in startup_checks(url): validate()

    def test_all_startup_gates_reject_adversarial_origins(self):
        for url in BAD_ORIGINS:
            for index, validate in enumerate(startup_checks(url)):
                with self.subTest(url=url, gate=index), self.assertRaises(ValueError): validate()

    def test_base_url_cannot_bypass_the_explicit_host_list(self):
        for url in BAD_ORIGINS:
            with self.subTest(url=url), self.assertRaises(ValueError):
                resolve_uat_auth_bypass_hosts(url, [HOST])
        for host in BAD_HEADERS + ("https://" + HOST, HOST + "/"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                resolve_uat_auth_bypass_hosts(ORIGIN, [host])
        self.assertEqual(resolve_uat_auth_bypass_hosts(ORIGIN, list(APPROVED_UAT_HOSTS)), set(APPROVED_UAT_HOSTS))

    def test_loopback_is_only_available_to_qa_persona_mode(self):
        for url in ("http://localhost:4173", "https://localhost", "http://127.0.0.1:3000"):
            checks = startup_checks(url)
            checks[2]()
            for index in (0, 1, 3, 4, 5, 6):
                with self.subTest(url=url, gate=index), self.assertRaises(ValueError): checks[index]()
        for url in ("ftp://localhost", "http://localhost:0", "http://localhost:65536", "http://localhost:04173",
                    "http://localhost/admin", "http://user@localhost:4173", "http://localhost.evil.test",
                    "http://127.0.0.2", "http://localhost:4173?", "http://localhost:4173#"):
            with self.subTest(url=url), self.assertRaises(ValueError): resolve_qa_access_authority(url)


class UatOriginRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def assert_bypass_denied(self, configured, host):
        db = AsyncMock()
        for target, endpoint in (("app.routers.auth.settings", uat_auto_login),
                                 ("app.routers.platform.settings", uat_platform_auto_login)):
            with patch(target, configured), self.assertRaises(HTTPException) as error:
                if endpoint is uat_auto_login: await endpoint(request(host), db)
                else: await endpoint(request(host), Response(), db)
            self.assertEqual(error.exception.status_code, 404)
        db.scalar.assert_not_awaited()
        db.execute.assert_not_awaited()

    async def test_invalid_configured_origin_fails_closed_at_runtime(self):
        for url in BAD_ORIGINS + ("http://localhost:4173",):
            with self.subTest(url=url):
                configured = runtime(url)
                try:
                    matching_host = urlsplit(url).hostname or HOST
                except ValueError:
                    matching_host = HOST
                # Reproduce the original bug with Host matching the malicious
                # configured origin, not just a mismatched legitimate Host.
                await self.assert_bypass_denied(configured, matching_host)
                with patch("app.services.mobile_store_policy.settings", configured):
                    self.assertFalse(uat_superadmin_store_access(NS(company_id=COMPANY, username="fixture-admin", is_superuser=True)))
                if url != "http://localhost:4173":
                    for target, guard in (("app.routers.auth.settings", _qa_access_guard),
                                          ("app.routers.platform.settings", _platform_qa_access_guard)):
                        with patch(target, configured), self.assertRaises(HTTPException) as error:
                            guard(request(matching_host), "k" * 32)
                        self.assertEqual(error.exception.status_code, 404)

    async def test_invalid_request_authorities_are_not_truncated_into_allowed_hosts(self):
        for host in BAD_HEADERS:
            with self.subTest(host=host):
                await self.assert_bypass_denied(runtime(), host)
                for target, guard in (("app.routers.auth.settings", _qa_access_guard),
                                      ("app.routers.platform.settings", _platform_qa_access_guard)):
                    with patch(target, runtime()), self.assertRaises(HTTPException) as error:
                        guard(request(host), "k" * 32)
                    self.assertEqual(error.exception.status_code, 404)

    async def test_runtime_bypass_rejects_unapproved_explicit_host(self):
        configured = runtime()
        configured.uat_auth_bypass_hosts = ["uat-unapproved.foodchainservice.com"]
        await self.assert_bypass_denied(configured, HOST)

    async def test_approved_runtime_hosts_still_reach_identity_lookup(self):
        for host in APPROVED_UAT_HOSTS:
            configured = runtime(f"https://{host}")
            with patch("app.services.mobile_store_policy.settings", configured):
                self.assertTrue(uat_superadmin_store_access(NS(company_id=COMPANY, username="fixture-admin", is_superuser=True)))
            db = AsyncMock()
            db.scalar.return_value = None
            with patch("app.routers.auth.settings", configured), self.assertRaises(HTTPException) as error:
                await uat_auto_login(request(host), db)
            self.assertEqual(error.exception.status_code, 503)  # Missing fixture user, not a host denial.
            db.scalar.assert_awaited_once()
            with patch("app.routers.platform.settings", configured), \
                 patch("app.routers.platform.PlatformAuthService") as service:
                service.return_value.issue_uat_bypass_session = AsyncMock(side_effect=HTTPException(503, "fixture-only"))
                with self.assertRaises(HTTPException) as error:
                    await uat_platform_auto_login(request(host), Response(), db)
                self.assertEqual(error.exception.status_code, 503)
                service.return_value.issue_uat_bypass_session.assert_awaited_once()

    async def test_qa_runtime_allows_only_configured_authority_including_loopback_port(self):
        for url, host in [(f"https://{h}", h) for h in APPROVED_UAT_HOSTS] + [
                ("http://localhost:4173", "localhost:4173"), ("https://127.0.0.1:3000", "127.0.0.1:3000")]:
            for target, guard in (("app.routers.auth.settings", _qa_access_guard),
                                  ("app.routers.platform.settings", _platform_qa_access_guard)):
                with patch(target, runtime(url)):
                    guard(request(host), "k" * 32)
                    with self.assertRaises(HTTPException) as error: guard(request(host + ":99"), "k" * 32)
                    self.assertEqual(error.exception.status_code, 404)
