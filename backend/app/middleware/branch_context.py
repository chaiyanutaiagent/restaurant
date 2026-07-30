from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class BranchContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        branch_id = request.headers.get("X-Branch-ID")
        request.state.branch_id = branch_id
        response = await call_next(request)
        if branch_id:
            response.headers["X-Branch-ID"] = branch_id
        return response
