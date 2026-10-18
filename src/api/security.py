"""Security building blocks for the web API: response headers, request-size cap, per-client rate limits.

Design rules (see docs/security.md):
* Nothing the browser sends is trusted: every field is length-limited and typed in schemas.py; unknown fields are refused.
* No user text is written to disk or logs. Conversations live in memory and expire (service.py).
* Responses are never cached (`Cache-Control: no-store` on /api) and carry a strict Content-Security-Policy.
* The client address comes from the socket unless TRUST_PROXY=1 says a trusted reverse proxy sets X-Forwarded-For.
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

MAX_BODY_BYTES = 16 * 1024

# Everything is served from this origin: no third-party scripts, styles, fonts or images (so no third party sees a visitor).
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; "
       "base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'")

HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


class SecurityHeaders(BaseHTTPMiddleware):
    def __init__(self, app, hsts: bool = False):
        super().__init__(app)
        self.hsts = hsts

    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        for k, v in HEADERS.items():
            resp.headers.setdefault(k, v)
        if self.hsts:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        if request.url.path.startswith("/api"):
            resp.headers["Cache-Control"] = "no-store"
        return resp


class BodyLimit(BaseHTTPMiddleware):
    """Refuse a request that announces a body above the cap, or a write without a length."""

    async def dispatch(self, request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            cl = request.headers.get("content-length")
            if cl is None or not cl.isdigit() or int(cl) > MAX_BODY_BYTES:
                return JSONResponse({"error": "request_too_large", "message": "The request is too large."}, status_code=413)
        return await call_next(request)


class RateLimiter:
    """Sliding window per (client, bucket). In memory: one process. A shared store is needed if the API runs on several machines."""

    def __init__(self, limits: dict[str, tuple[int, int]], clock=time.monotonic):
        self.limits, self.clock = limits, clock
        self.hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, client: str, bucket: str) -> int | None:
        """None when allowed, else the seconds to wait."""
        limit, window = self.limits[bucket]
        now = self.clock()
        with self.lock:
            q = self.hits[(client, bucket)]
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                return max(1, int(q[0] + window - now) + 1)
            q.append(now)
            if len(self.hits) > 20000:                      # bound the memory a flood of addresses can use
                for k in [k for k, v in self.hits.items() if not v or v[-1] <= now - 3600][:10000]:
                    self.hits.pop(k, None)
        return None


def client_ip(request) -> str:
    if os.environ.get("TRUST_PROXY") == "1":
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


DEFAULT_LIMITS = {"agent": (8, 60), "agent_hour": (40, 3600), "lookup": (60, 60), "bill": (30, 60), "feedback": (20, 60)}
