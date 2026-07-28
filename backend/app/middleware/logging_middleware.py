"""
Logging Middleware — Structured request/response logging.
"""

import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.middleware")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Logs every request with method, path, status code, and latency."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()

        # Process the request
        response: Response = await call_next(request)

        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000

        logger.info(
            f"{request.method} {request.url.path} "
            f"→ {response.status_code} "
            f"({latency_ms:.1f}ms) "
            f"[{request.client.host if request.client else 'unknown'}]"
        )

        return response
