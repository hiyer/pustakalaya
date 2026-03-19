# pustakalaya/web/auth.py
import base64

import pam
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class PamBasicAuthMiddleware(BaseHTTPMiddleware):
    """Require HTTP Basic Auth validated via PAM login service."""

    async def dispatch(self, request: Request, call_next) -> Response:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Basic "):
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="pustakalaya"'},
            )
        try:
            credentials = base64.b64decode(auth_header[6:]).decode("utf-8")
            username, password = credentials.split(":", 1)
        except Exception:
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="pustakalaya"'},
            )

        if not pam.authenticate(username, password, service="login"):
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="pustakalaya"'},
            )

        return await call_next(request)
