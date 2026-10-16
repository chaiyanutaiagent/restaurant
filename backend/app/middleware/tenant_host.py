"""Bounded staff-only UAT company alias; existing public QR origins stay unchanged.

This is an additional host boundary, not a replacement for route authentication,
revocation, branch/brand permissions or row-level tenant checks.
"""
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings
from app.utils.security import decode_token

HOST = "sketchbiz.foodchainservice.com"
COMPANY_ID = "1b8a1818-44d6-4d5f-9d22-e5e17b23c081"
BUSINESS_PATH = "/api/v1/membership/businesses/sketch-biz"


def check_company_token(token: str, expected_type: str | None = None) -> None:
    payload = decode_token(token)
    if (payload.get("company_id") != COMPANY_ID or payload.get("qa_mode")
            or (expected_type and payload.get("type") != expected_type)):
        raise HTTPException(403, "This hostname is restricted to Sketch Biz staff")


class TenantHostMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.hostname != HOST:
            return await call_next(request)
        uat_host = urlsplit(settings.saas_public_base_url).hostname or ""
        if settings.environment != "development" or not uat_host.startswith("uat-"):
            return JSONResponse({"detail": "Company UAT hostname is not enabled here"}, status_code=404)
        path = request.url.path.rstrip("/")
        if path == "/health" or path.startswith("/uploads/"):
            return await call_next(request)
        try:
            # Platform, bypass and provisioning stay on their original hostnames.
            if (not path.startswith("/api/") or path.startswith("/api/v1/platform")
                    or path.startswith("/api/v1/auth/qa/")
                    or path.startswith("/api/v1/auth/uat/")):
                raise HTTPException(404, "Not found")
            company_header = request.headers.get("x-company-id")
            if company_header and company_header != COMPANY_ID:
                raise HTTPException(403, "Company does not match hostname")
            if path == BUSINESS_PATH and request.method == "GET":
                return await call_next(request)
            if path == "/api/v1/auth/login" and request.method == "POST":
                body = await request.json()
                if not isinstance(body, dict) or str(body.get("company_id", "")) != COMPANY_ID:
                    raise HTTPException(403, "Company does not match hostname")
            elif path == "/api/v1/auth/refresh" and request.method == "POST":
                body = await request.json()
                if not isinstance(body, dict) or not isinstance(body.get("refresh_token"), str):
                    raise HTTPException(400, "Invalid refresh request")
                check_company_token(body["refresh_token"], "refresh")
            else:
                authorization = request.headers.get("authorization", "")
                scheme, _, token = authorization.partition(" ")
                if scheme.lower() != "bearer" or not token:
                    raise HTTPException(401, "Sketch Biz staff login required")
                check_company_token(token, "access")
            device_auth = request.headers.get("x-device-authorization")
            if device_auth:
                scheme, _, token = device_auth.partition(" ")
                if scheme.lower() != "bearer" or not token:
                    raise HTTPException(401, "Invalid device credential")
                check_company_token(token)
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        except (ValueError, TypeError):
            return JSONResponse({"detail": "Invalid request"}, status_code=400)
        response = await call_next(request)
        response.headers["X-Foodchainservice-Environment"] = "uat"
        return response
