import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Literal

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.limits import LimitHit
from app.rag import pipeline, store
from app.rag.pipeline import Services

log = logging.getLogger(__name__)


def _db_ok() -> bool:
    try:
        with psycopg.connect(settings.database_url, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
        return True
    except psycopg.Error:
        return False


def error(status: int, code: str, message: str, retry_after: int | None = None) -> JSONResponse:
    """The one error shape every endpoint uses."""
    body: dict = {"code": code, "message": message}
    headers = {}
    if retry_after is not None:
        body["retry_after"] = retry_after
        headers["Retry-After"] = str(retry_after)
    return JSONResponse({"error": body}, status_code=status, headers=headers)


def client_ip(request: Request) -> str:
    """The real client IP. Only the proxies we run (CloudFront, Caddy) are trusted: anything
    earlier in X-Forwarded-For was written by the client and could be forged."""
    hops = settings.trusted_proxy_hops
    forwarded = [
        p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()
    ]
    if hops and len(forwarded) >= hops:
        return forwarded[-hops]
    return request.client.host if request.client else "unknown"


class AskRequest(BaseModel):
    question: str = Field(max_length=settings.max_question_chars)

    @field_validator("question")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Question is empty.")
        return v


class FeedbackRequest(BaseModel):
    query_id: uuid.UUID
    rating: Literal[-1, 1]


def create_app(services: Services | None = None) -> FastAPI:
    """services=None builds the real ones at startup (tests pass fakes instead)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.services = services
        if services is None:
            try:
                from app.services import build_services

                app.state.services = build_services()
                log.info(
                    "services ready: %d chunks indexed",
                    len(app.state.services.retriever.keyword_index.docs),
                )
            except Exception:  # noqa: BLE001 - start anyway; /api/health reports it
                log.exception("could not build services at startup; will retry on first request")
        yield

    app = FastAPI(
        title="CPSC Compliance Assistant",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.services = services

    def get_services() -> Services | None:
        if app.state.services is None:
            try:
                from app.services import build_services

                app.state.services = build_services()
            except Exception:  # noqa: BLE001
                log.exception("services still unavailable")
        return app.state.services

    @app.middleware("http")
    async def visitor_cookie(request: Request, call_next):
        vid = request.cookies.get(settings.visitor_cookie)
        try:
            uuid.UUID(vid or "")
        except ValueError:
            vid = None
        request.state.visitor_id = vid or str(uuid.uuid4())
        response = await call_next(request)
        if vid is None:
            response.set_cookie(
                settings.visitor_cookie,
                request.state.visitor_id,
                max_age=60 * 60 * 24 * 365,
                httponly=True,
                secure=settings.env == "prod",
                samesite="lax",
            )
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_input(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        if first.get("type") == "string_too_long":
            msg = f"Questions can be at most {settings.max_question_chars} characters."
        else:
            msg = str(first.get("msg", "Invalid request.")).removeprefix("Value error, ")
        return error(422, "invalid_input", msg)

    @app.post("/api/ask")
    async def ask(body: AskRequest, request: Request):
        services = get_services()
        if services is None:
            return error(503, "upstream_error", "The service is starting up. Try again shortly.")
        visitor, ip = request.state.visitor_id, client_ip(request)
        hit: LimitHit | None = services.limiter.check_burst(
            visitor
        ) or services.limiter.check_daily(visitor, ip)
        if hit:
            return error(429, hit.code, hit.message, hit.retry_after)

        async def events() -> AsyncIterator[str]:
            try:
                async for event in pipeline.answer(services, body.question, visitor, ip):
                    kind = event.pop("type")
                    yield f"event: {kind}\ndata: {json.dumps(event)}\n\n"
            except Exception:  # noqa: BLE001 - the stream has started: report in-band
                log.exception("ask failed")
                err = {
                    "code": "upstream_error",
                    "message": "Something went wrong. Please try again.",
                }
                yield f"event: error\ndata: {json.dumps(err)}\n\n"

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/usage")
    def usage(request: Request):
        services = get_services()
        if services is None:
            return error(503, "upstream_error", "The service is starting up.")
        return asdict(services.limiter.usage(request.state.visitor_id))

    @app.get("/api/documents")
    def documents():
        return store.list_documents()

    @app.get("/api/documents/{doc_id}")
    def document(doc_id: str):
        doc = store.get_document(doc_id)
        return doc if doc else error(404, "not_found", f"No document {doc_id}.")

    @app.get("/api/sources/{chunk_id:path}")
    def source(chunk_id: str):
        chunk = store.get_chunk(chunk_id)
        return chunk if chunk else error(404, "not_found", f"No source {chunk_id}.")

    @app.post("/api/feedback", status_code=204)
    def feedback(body: FeedbackRequest) -> Response:
        store.insert_feedback(str(body.query_id), body.rating)
        return Response(status_code=204)

    @app.get("/api/health")
    def health() -> JSONResponse:
        db = _db_ok()
        services = app.state.services
        checks = {
            "db": db,
            "llm_mode": settings.llm_mode,
            "chunks_indexed": len(services.retriever.keyword_index.docs) if services else 0,
        }
        status = 200 if db else 503
        body = {"status": "ok" if db else "degraded", "env": settings.env, **checks}
        return JSONResponse(body, status_code=status)

    return app


app = create_app()
