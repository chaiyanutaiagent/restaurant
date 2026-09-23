from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from app.config import validate_qa_access_mode_config, validate_uat_auth_bypass_config
from app.routers.auth import _qa_access_guard
from app.routers.platform import _platform_qa_access_guard


class UatAuthBypassConfigTests(unittest.TestCase):
    company_id = uuid.UUID("1b8a1818-44d6-4d5f-9d22-e5e17b23c081")

    def test_disabled_bypass_is_safe_in_any_environment(self) -> None:
        validate_uat_auth_bypass_config(
            environment="production",
            enabled=False,
            public_base_url="https://foodchainservice.com",
            company_id=None,
            username=None,
            platform_username=None,
        )

    def test_enabled_bypass_accepts_only_https_uat_development(self) -> None:
        validate_uat_auth_bypass_config(
            environment="development",
            enabled=True,
            public_base_url="https://uat-pos.foodchainservice.com",
            company_id=self.company_id,
            username="admin",
            platform_username="qa.platform-admin",
        )

        invalid_cases = (
            ("production", "https://uat-pos.foodchainservice.com"),
            ("staging", "https://uat-pos.foodchainservice.com"),
            ("development", "http://uat-pos.foodchainservice.com"),
            ("development", "https://foodchainservice.com"),
        )
        for environment, public_base_url in invalid_cases:
            with self.subTest(environment=environment, public_base_url=public_base_url):
                with self.assertRaises(ValueError):
                    validate_uat_auth_bypass_config(
                        environment=environment,
                        enabled=True,
                        public_base_url=public_base_url,
                        company_id=self.company_id,
                        username="admin",
                        platform_username="qa.platform-admin",
                    )


class QaAccessModeConfigTests(unittest.TestCase):
    company_id = uuid.UUID("1b8a1818-44d6-4d5f-9d22-e5e17b23c081")
    key = "q" * 32
    personas = {"company_owner": "uat.company-owner"}
    platform_personas = {"platform_admin": "uat.platform-admin"}

    def test_disabled_mode_is_safe_without_runtime_key(self) -> None:
        validate_qa_access_mode_config(
            environment="production",
            enabled=False,
            public_base_url="https://foodchainservice.com",
            access_key=None,
            company_id=None,
            personas={},
            platform_personas={},
        )

    def test_enabled_mode_accepts_only_local_or_https_uat(self) -> None:
        for base_url in ("http://localhost:4173", "https://uat-pos.foodchainservice.com"):
            validate_qa_access_mode_config(
                environment="development",
                enabled=True,
                public_base_url=base_url,
                access_key=self.key,
                company_id=self.company_id,
                personas=self.personas,
                platform_personas=self.platform_personas,
            )

    def test_production_and_public_host_fail_closed(self) -> None:
        invalid = (
            ("production", "https://uat-pos.foodchainservice.com"),
            ("development", "https://foodchainservice.com"),
            ("staging", "https://uat-pos.foodchainservice.com"),
        )
        for environment, base_url in invalid:
            with self.subTest(environment=environment, base_url=base_url):
                with self.assertRaises(ValueError):
                    validate_qa_access_mode_config(
                        environment=environment,
                        enabled=True,
                        public_base_url=base_url,
                        access_key=self.key,
                        company_id=self.company_id,
                        personas=self.personas,
                        platform_personas=self.platform_personas,
                    )

    def test_runtime_key_and_explicit_personas_are_required(self) -> None:
        with self.assertRaises(ValueError):
            validate_qa_access_mode_config(
                environment="development",
                enabled=True,
                public_base_url="https://uat-pos.foodchainservice.com",
                access_key="short",
                company_id=self.company_id,
                personas=self.personas,
                platform_personas=self.platform_personas,
            )

    def test_runtime_channel_requires_exact_host_and_key(self) -> None:
        runtime = SimpleNamespace(
            qa_access_mode_enabled=True,
            environment="development",
            saas_public_base_url="https://uat-pos.foodchainservice.com",
            qa_access_key=self.key,
        )
        request = Request({
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"host", b"uat-pos.foodchainservice.com")],
        })
        for target in ("app.routers.auth.settings", "app.routers.platform.settings"):
            with patch(target, runtime):
                guard = _qa_access_guard if target.endswith("auth.settings") else _platform_qa_access_guard
                guard(request, self.key)
                with self.assertRaises(HTTPException) as raised:
                    guard(request, "wrong")
                self.assertEqual(raised.exception.status_code, 404)

    def test_enabled_bypass_requires_explicit_identity(self) -> None:
        for company_id, username, platform_username in (
            (None, "admin", "qa.platform-admin"),
            (self.company_id, None, "qa.platform-admin"),
            (self.company_id, " ", "qa.platform-admin"),
            (self.company_id, "admin", None),
            (self.company_id, "admin", " "),
        ):
            with self.subTest(company_id=company_id, username=username, platform_username=platform_username):
                with self.assertRaises(ValueError):
                    validate_uat_auth_bypass_config(
                        environment="development",
                        enabled=True,
                        public_base_url="https://uat-pos.foodchainservice.com",
                        company_id=company_id,
                        username=username,
                        platform_username=platform_username,
                    )


if __name__ == "__main__":
    unittest.main()
