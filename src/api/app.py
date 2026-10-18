"""Customs Copilot web API (FastAPI). Same-origin JSON; the web app proxies /api to this process.

    python -m src.api                      # http://127.0.0.1:8000 (development)

Endpoints: GET /api/meta, POST /api/agent/ask, POST /api/agent/answer, POST /api/lookup, POST /api/bill, POST /api/feedback.
Security notes: docs/security.md. The API never prints, stores or caches what users type except what they consent to in feedback.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .schemas import AnswerIn, AskIn, BillIn, FeedbackIn, LookupIn
from .security import DEFAULT_LIMITS, BodyLimit, RateLimiter, SecurityHeaders, client_ip
from .service import AgentService, Busy, FeedbackStore

log = logging.getLogger("customs_api")
DISCLAIMER = ("Decision support only. This is not an FBR service and not legal or customs advice. Check with Pakistan Customs or a licensed customs agent "
              "before you import. What you type is sent to the AI provider that reads it; do not enter names, phone numbers or other personal data.")


def _today() -> str:
    return dt.date.today().isoformat()


def create_app(service: AgentService | None = None, limiter: RateLimiter | None = None, feedback: FeedbackStore | None = None, *,
               lookup_fn=None, bill_fn=None, allowed_hosts: list[str] | None = None, docs: bool | None = None) -> FastAPI:
    docs = docs if docs is not None else os.environ.get("API_DOCS") == "1"
    app = FastAPI(title="Customs Copilot API", docs_url="/api/docs" if docs else None, redoc_url=None, openapi_url="/api/openapi.json" if docs else None)
    svc = service or AgentService()
    lim = limiter or RateLimiter(DEFAULT_LIMITS)
    fb = feedback
    hosts = allowed_hosts or [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if h.strip()]

    app.add_middleware(BodyLimit)
    app.add_middleware(SecurityHeaders, hsts=os.environ.get("API_HSTS") == "1")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    def limited(request: Request, *buckets: str) -> None:
        ip = client_ip(request)
        for b in buckets:
            wait = lim.check(ip, b)
            if wait is not None:
                raise HTTPException(429, detail="Too many requests. Please wait a little and try again.", headers={"Retry-After": str(wait)})

    def get_lookup():
        if lookup_fn is not None:
            return lookup_fn
        from src.tools.code_lookup import search_codes

        return search_codes

    def get_bill():
        if bill_fn is not None:
            return bill_fn
        from src.tools import compute_duty

        return compute_duty

    @app.exception_handler(RequestValidationError)
    async def _invalid(request: Request, exc: RequestValidationError):
        fields = sorted({".".join(str(x) for x in e["loc"][1:]) or "body" for e in exc.errors()})      # field names only, never the values
        return JSONResponse({"error": "invalid_request", "message": "Some fields are missing or not valid.", "fields": fields}, status_code=422)

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException):
        return JSONResponse({"error": "http_error", "message": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))

    def fail(exc: Exception, where: str) -> HTTPException:
        from src.agent.llm import LLMBudgetExceeded, LLMRateLimited, LLMUnavailable

        if isinstance(exc, Busy):
            return HTTPException(503, detail=str(exc), headers={"Retry-After": "60"})
        if isinstance(exc, (LLMRateLimited, LLMBudgetExceeded, LLMUnavailable)):
            return HTTPException(503, detail="The AI service is not available right now. Please try again later.", headers={"Retry-After": "120"})
        rid = uuid.uuid4().hex[:12]
        log.error("%s failed [%s]: %s", where, rid, type(exc).__name__)          # the type only: messages can quote user text
        return HTTPException(500, detail=f"Something went wrong (reference {rid}).")

    @app.get("/api/meta")
    def meta():
        from src.tools._util import coverage, get_conn

        lo, hi = coverage(get_conn())
        return {"covers_from": lo, "covers_to": hi, "today": _today(), "disclaimer": DISCLAIMER}

    @app.post("/api/agent/ask")
    def ask(body: AskIn, request: Request):
        limited(request, "agent", "agent_hour")
        try:
            return svc.ask(body.question, body.date or _today())
        except Exception as e:
            raise fail(e, "ask") from None

    @app.post("/api/agent/answer")
    def answer(body: AnswerIn, request: Request):
        limited(request, "agent", "agent_hour")
        if not body.answers and not body.reply:
            raise HTTPException(422, detail="Please answer at least one question.")
        try:
            return svc.answer(body.thread_id, body.answers, body.reply)
        except KeyError:
            raise HTTPException(404, detail="This conversation has expired. Please start again.") from None
        except Exception as e:
            raise fail(e, "answer") from None

    @app.post("/api/lookup")
    def lookup(body: LookupIn, request: Request):
        limited(request, "lookup")
        try:
            return get_lookup()(body.query, body.date or _today(), body.k, body.chapter, body.cd_pct)
        except Exception as e:
            raise fail(e, "lookup") from None

    @app.post("/api/bill")
    def bill(body: BillIn, request: Request):
        limited(request, "bill")
        try:
            return get_bill()(body.code, body.value_pkr, body.date or _today(), importer=body.importer or None, quantity=body.quantity,
                              quantity_unit=body.unit, goods=body.goods or None, claimed_rules=body.claimed_rules or None)
        except Exception as e:
            raise fail(e, "bill") from None

    @app.post("/api/feedback", status_code=204)
    def feedback_in(body: FeedbackIn, request: Request):
        limited(request, "feedback")
        nonlocal fb
        try:
            fb = fb or FeedbackStore()
            fb.add(body.helpful, body.thread_id, body.code, body.note, body.consent_to_store_note)
        except Exception as e:
            raise fail(e, "feedback") from None

    return app
