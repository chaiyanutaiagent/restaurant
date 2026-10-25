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
THE_LOFT_COMPANY_ID = "9b766136-c10f-4ef4-856f-b2f95b943f5e"
TENANT_HOSTS = {
    HOST: (COMPANY_ID, "sketch-biz"),
    "theloft.foodchainservice.com": (THE_LOFT_COMPANY_ID, "theloft"),
}


def check_company_token(token: str, expected_type: str | None = None, *, company_id: str = COMPANY_ID) -> None:
    payload = decode_token(token)
    if (payload.get("company_id") != company_id or payload.get("qa_mode")
            or (expected_type and payload.get("type") != expected_type)):
        raise HTTPException(403, "Company does not match hostname")


class TenantHostMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        tenant = TENANT_HOSTS.get(request.url.hostname or "")
        if tenant is None:
            return await call_next(request)
        company_id, business_slug = tenant
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
            if company_header and company_header != company_id:
                raise HTTPException(403, "Company does not match hostname")
            if path == f"/api/v1/membership/businesses/{business_slug}" and request.method == "GET":
                return await call_next(request)
            if path == "/api/v1/auth/login" and request.method == "POST":
                body = await request.json()
                if not isinstance(body, dict) or str(body.get("company_id", "")) != company_id:
                    raise HTTPException(403, "Company does not match hostname")
            elif path == "/api/v1/auth/refresh" and request.method == "POST":
                body = await request.json()
                if not isinstance(body, dict) or not isinstance(body.get("refresh_token"), str):
                    raise HTTPException(400, "Invalid refresh request")
                check_company_token(body["refresh_token"], "refresh", company_id=company_id)
            else:
                authorization = request.headers.get("authorization", "")
                scheme, _, token = authorization.partition(" ")
                if scheme.lower() != "bearer" or not token:
                    raise HTTPException(401, "Company staff login required")
                check_company_token(token, "access", company_id=company_id)
            device_auth = request.headers.get("x-device-authorization")
            if device_auth:
                scheme, _, token = device_auth.partition(" ")
                if scheme.lower() != "bearer" or not token:
                    raise HTTPException(401, "Invalid device credential")
                check_company_token(token, company_id=company_id)
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        except (ValueError, TypeError):
            return JSONResponse({"detail": "Invalid request"}, status_code=400)
        response = await call_next(request)
        response.headers["X-Foodchainservice-Environment"] = "uat"
        return response
