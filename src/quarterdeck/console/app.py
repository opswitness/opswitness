"""FastAPI shell for the loopback-only Quarterdeck total console."""

from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Literal

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from quarterdeck.config import Settings
from quarterdeck.console.schemas import (
    ApprovalDecisionRequest,
    ConfirmRequest,
    DeletePlanRequest,
    MailAuthorizationRequest,
    MailDisableRequest,
    MailOAuthClientRequest,
    OrganizationRevisionRequest,
    PlanRequest,
    RevisePlanRequest,
    TelegramActionRequest,
    TelegramConfigureRequest,
)
from quarterdeck.console.service import ConsoleConflict, ConsoleService, ConsoleUnavailable
from quarterdeck.console.store import PlanNotFound


def create_app(
    settings: Settings | None = None,
    *,
    service: ConsoleService | None = None,
) -> FastAPI:
    settings = settings or Settings()
    owned_service = service is None
    service = service or ConsoleService(settings)
    csrf_token = secrets.token_urlsafe(32)
    allowed_hosts = {"127.0.0.1", "localhost", "::1"}
    allowed_origins = {
        f"http://127.0.0.1:{settings.console.port}",
        f"http://localhost:{settings.console.port}",
    }

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        acquired_here = False
        try:
            acquired_here = await run_in_threadpool(service.acquire_instance_lease)
            await run_in_threadpool(service.recover_startup)
            yield
        finally:
            if owned_service:
                service.close()
            elif acquired_here:
                service.release_instance_lease()

    app = FastAPI(
        title="Quarterdeck Console",
        version="1",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.console_service = service
    app.state.csrf_token = csrf_token

    @app.middleware("http")
    async def security_boundary(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.url.hostname not in allowed_hosts:
            return JSONResponse({"detail": "host denied"}, status_code=400)
        if request.url.path.startswith("/api/") and request.method not in {
            "GET",
            "HEAD",
            "OPTIONS",
        }:
            origin = request.headers.get("origin")
            if origin is not None and origin not in allowed_origins:
                return JSONResponse({"detail": "origin denied"}, status_code=403)
            if request.headers.get("x-qd-csrf") != csrf_token:
                return JSONResponse({"detail": "csrf token required"}, status_code=403)
            if not request.headers.get("content-type", "").startswith("application/json"):
                return JSONResponse({"detail": "application/json required"}, status_code=415)
        response: Response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

    @app.exception_handler(PlanNotFound)
    async def not_found(_: Request, exc: PlanNotFound) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(ConsoleConflict)
    async def conflict(_: Request, exc: ConsoleConflict) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(ConsoleUnavailable)
    async def unavailable(_: Request, exc: ConsoleUnavailable) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "exposure": "loopback"}

    @app.get("/api/v1/bootstrap")
    async def bootstrap() -> dict:
        payload = await run_in_threadpool(service.dashboard)
        payload["csrf_token"] = csrf_token
        return payload

    @app.get("/api/v1/plans")
    async def plans() -> list[dict]:
        return [row.model_dump(mode="json") for row in await run_in_threadpool(service.list_plans)]

    @app.post("/api/v1/plans", status_code=status.HTTP_202_ACCEPTED)
    async def create_plan(
        body: PlanRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        try:
            record = await run_in_threadpool(service.request_plan, body)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return record.model_dump(mode="json")

    @app.get("/api/v1/plans/{plan_id}")
    async def get_plan(plan_id: str) -> dict:
        record = await run_in_threadpool(service.get_plan, plan_id)
        return record.model_dump(mode="json")

    @app.post("/api/v1/plans/{plan_id}/revise", status_code=status.HTTP_202_ACCEPTED)
    async def revise_plan(
        plan_id: str,
        body: RevisePlanRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        record = await run_in_threadpool(service.request_plan_revision, plan_id, body)
        return record.model_dump(mode="json")

    @app.post(
        "/api/v1/plans/{plan_id}/organization",
        status_code=status.HTTP_201_CREATED,
    )
    async def revise_plan_organization(
        plan_id: str,
        body: OrganizationRevisionRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        record = await run_in_threadpool(service.revise_plan_organization, plan_id, body)
        return record.model_dump(mode="json")

    @app.post("/api/v1/plans/{plan_id}/confirm", status_code=status.HTTP_202_ACCEPTED)
    async def confirm_plan(
        plan_id: str,
        body: ConfirmRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        record = await run_in_threadpool(service.confirm_plan, plan_id, body)
        return record.model_dump(mode="json")

    @app.delete("/api/v1/plans/{plan_id}")
    async def delete_plan(
        plan_id: str,
        body: DeletePlanRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        return await run_in_threadpool(service.delete_plan, plan_id, body)

    @app.get("/api/v1/providers")
    async def providers() -> dict:
        return await run_in_threadpool(service.provider_statuses)

    @app.post("/api/v1/providers/{provider}/connect", status_code=status.HTTP_202_ACCEPTED)
    async def connect_provider(
        provider: Literal["openai", "anthropic"],
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        job = await run_in_threadpool(service.request_provider_connection, provider)
        return job.model_dump(mode="json")

    @app.get("/api/v1/provider-connections/{job_id}")
    async def provider_connection(job_id: str) -> dict:
        job = await run_in_threadpool(service.get_provider_connection, job_id)
        return job.model_dump(mode="json")

    @app.get("/api/v1/approvals")
    async def approvals() -> list[dict]:
        return await run_in_threadpool(service.list_pending_approvals)

    @app.post("/api/v1/approvals/{approval_id}/decision")
    async def decide_approval(
        approval_id: str,
        body: ApprovalDecisionRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        return await run_in_threadpool(service.decide_approval, approval_id, body)

    @app.post("/api/v1/mail-summary", status_code=status.HTTP_202_ACCEPTED)
    async def create_mail_summary(
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        job = await run_in_threadpool(service.request_mail_summary)
        return job.model_dump(mode="json")

    @app.get("/api/v1/mail-summary/{job_id}")
    async def get_mail_summary(job_id: str) -> dict:
        job = await run_in_threadpool(service.get_mail_summary, job_id)
        return job.model_dump(mode="json")

    @app.get("/api/v1/mail-authorization/status")
    async def mail_authorization_status() -> dict:
        return await run_in_threadpool(service.mail_setup_status)

    @app.post("/api/v1/mail-authorization", status_code=status.HTTP_202_ACCEPTED)
    async def create_mail_authorization(
        body: MailAuthorizationRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        job = await run_in_threadpool(service.request_mail_authorization, body)
        return job.model_dump(mode="json")

    @app.post("/api/v1/mail-authorization/client")
    async def configure_mail_oauth_client(
        body: MailOAuthClientRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        return await run_in_threadpool(service.configure_mail_oauth_client, body)

    @app.post("/api/v1/mail-authorization/disable")
    async def disable_mail(
        body: MailDisableRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del body, x_qd_csrf
        return await run_in_threadpool(service.disable_mail)

    @app.get("/api/v1/mail-authorization/{job_id}")
    async def get_mail_authorization(job_id: str) -> dict:
        job = await run_in_threadpool(service.get_mail_authorization, job_id)
        return job.model_dump(mode="json")

    @app.get("/api/v1/telegram/status")
    async def telegram_status() -> dict:
        return await run_in_threadpool(service.telegram_setup_status)

    @app.post("/api/v1/telegram/configure")
    async def configure_telegram(
        body: TelegramConfigureRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        return await run_in_threadpool(service.configure_telegram, body)

    @app.post("/api/v1/telegram/test")
    async def test_telegram(
        body: TelegramActionRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del body, x_qd_csrf
        return await run_in_threadpool(service.test_telegram)

    @app.post("/api/v1/telegram/disable")
    async def disable_telegram(
        body: TelegramActionRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del body, x_qd_csrf
        return await run_in_threadpool(service.disable_telegram)

    static_dir = Path(__file__).with_name("static")
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="console-assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str) -> Response:
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        candidate = static_dir / path
        if path and candidate.is_file() and static_dir in candidate.resolve().parents:
            return FileResponse(candidate)
        index = static_dir / "index.html"
        if index.exists():
            return FileResponse(index)
        return JSONResponse(
            {"detail": "console frontend is not built; run npm run build in console-ui"},
            status_code=503,
        )

    return app
