"""FastAPI shell for the local-first OpsWitness total console."""

from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager
from contextlib import suppress
from ipaddress import ip_address
from pathlib import Path
from typing import AsyncIterator, Literal
from urllib.parse import quote

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from pydantic import ValidationError
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from opswitness.config import Settings
from opswitness.console.access import (
    console_allowed_hosts,
    console_local_origins,
    console_public_origins,
    console_public_url,
)
from opswitness.console.pairing import (
    PAIRING_COOKIE,
    DevicePairingStore,
    InvalidPairingCode,
    PairingLocked,
    PairingStateError,
)
from opswitness.console.schemas import (
    AgentContractPreviewRequest,
    AgentContractRevisionRequest,
    AgentGraphRevisionRequest,
    ApprovalDecisionRequest,
    ArtifactSignoffRequest,
    ConfirmRequest,
    ContinueRunRequest,
    DeletePlanRequest,
    DesktopDrainRequest,
    EraseRunRequest,
    ExecutionApprovalModeRequest,
    ExecutionControlRequest,
    ExecutionProfileRevisionRequest,
    ForkPlanRequest,
    LibraryCardDecisionRequestV1,
    LibraryCardJobRequestV1,
    LibraryCollectionCreateV1,
    LibraryCollectionRevisionRequestV1,
    LibraryDocumentMetadataUpdateV1,
    LibraryH5ExportPreviewRequestV1,
    LibraryH5ExportRequestV1,
    LibraryImportCommitRequestV1,
    LibraryImportCreateRequestV1,
    LibraryPlanRequestV1,
    LibrarySearchRequestV1,
    LibrarySemanticModelDownloadRequestV1,
    MailAuthorizationRequest,
    MailDisableRequest,
    MailOAuthClientRequest,
    OnboardingFirstWorkRequest,
    OnboardingMigrationRequest,
    OnboardingProviderRequest,
    OrganizationRevisionRequest,
    PairingClaimRequest,
    PairingMutationRequest,
    PlanRequest,
    ProcessMemoryProposalRequest,
    ProjectLibraryItem,
    ProjectLibraryItemPreview,
    ProjectLibraryMetadataUpdate,
    ProviderConnectionRequest,
    RecoveryCheckRequest,
    RecoveryDecisionRequest,
    RerunPlanRequest,
    RevisePlanRequest,
    RuntimeInputAnswerRequest,
    RuntimeRevisionRequest,
    TaskTemplateArchiveRequest,
    TaskTemplateFromPlanRequest,
    TaskTemplateSaveRequest,
    TelegramActionRequest,
    TelegramConfigureRequest,
    TeamBlueprintArchiveRequest,
    TeamBlueprintSaveRequest,
    WorkspaceMemoryCandidateRequest,
    WorkspaceMemoryDecisionRequest,
    WorkspaceMemoryRollbackRequest,
)
from opswitness.console.service import (
    ConsoleConflict,
    ConsoleService,
    ConsoleUnavailable,
    RuntimeArtifactNotFound,
    RuntimeArtifactPreviewError,
)
from opswitness.console.store import (
    BlueprintNotFound,
    PlanNotFound,
    TaskTemplateNotFound,
    WorkspaceMemoryNotFound,
)


def create_app(
    settings: Settings | None = None,
    *,
    service: ConsoleService | None = None,
    pairing_store: DevicePairingStore | None = None,
) -> FastAPI:
    settings = settings or Settings()
    owned_service = service is None
    service = service or ConsoleService(settings)
    csrf_token = secrets.token_urlsafe(32)
    allowed_hosts = console_allowed_hosts(settings.console)
    local_origins = console_local_origins(settings.console)
    public_origins = console_public_origins(settings.console)
    private_exposure = settings.console.exposure == "private"
    pairing_store = pairing_store or DevicePairingStore(
        settings.console.state_dir / "pairing",
        code_ttl_seconds=settings.console.pairing_code_ttl_seconds,
        session_days=settings.console.device_session_days,
    )
    public_pairing_paths = {
        "/api/health",
        "/api/v1/pairing/status",
        "/api/v1/pairing/claim",
        "/pair",
        "/pair.css",
        "/pair.js",
        "/manifest.webmanifest",
        "/sw.js",
        "/offline.html",
        "/offline.css",
        "/apple-touch-icon.png",
    }

    def is_loopback_client(request: Request) -> bool:
        if request.client is None:
            return False
        try:
            return ip_address(request.client.host).is_loopback
        except ValueError:
            return False

    def is_public_pairing_path(path: str) -> bool:
        return path in public_pairing_paths or path.startswith("/icons/")

    def is_effective_https(request: Request) -> bool:
        if settings.console.private_transport == "direct_tls":
            return request.url.scheme == "https"
        hostname = (request.url.hostname or "").rstrip(".").lower()
        return (
            is_loopback_client(request)
            and hostname == settings.console.public_host.rstrip(".").lower()
            and request.headers.get("x-forwarded-proto") == "https"
        )

    def secure_response(response: Response, request: Request) -> Response:
        if request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif request.url.path == "/sw.js":
            response.headers["Cache-Control"] = "no-cache"
            response.headers["Service-Worker-Allowed"] = "/"
        elif request.url.path in {
            "/manifest.webmanifest",
            "/offline.html",
            "/offline.css",
            "/apple-touch-icon.png",
        } or request.url.path.startswith("/icons/"):
            response.headers["Cache-Control"] = "public, max-age=3600"
        else:
            response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'self'; manifest-src 'self'; worker-src 'self'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        if private_exposure and is_effective_https(request):
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        acquired_here = False
        recovery_monitor: asyncio.Task[None] | None = None

        async def monitor_recovery() -> None:
            while True:
                await asyncio.sleep(15)
                try:
                    await run_in_threadpool(service.monitor_recovery_cycle)
                except (ConsoleConflict, ConsoleUnavailable, OSError, ValueError):
                    # The next bounded cycle retries; the service records Work-level evidence.
                    pass

        try:
            acquired_here = await run_in_threadpool(service.acquire_instance_lease)
            await run_in_threadpool(service.recover_startup)
            recovery_monitor = asyncio.create_task(
                monitor_recovery(),
                name="opswitness-recovery-monitor",
            )
            yield
        finally:
            if recovery_monitor is not None:
                recovery_monitor.cancel()
                with suppress(asyncio.CancelledError):
                    await recovery_monitor
            if owned_service:
                service.close()
            elif acquired_here:
                service.release_instance_lease()

    app = FastAPI(
        title="OpsWitness Console",
        version="1",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.console_service = service
    app.state.csrf_token = csrf_token
    app.state.pairing_store = pairing_store

    @app.middleware("http")
    async def security_boundary(request: Request, call_next):  # type: ignore[no-untyped-def]
        hostname = (request.url.hostname or "").rstrip(".").lower()
        if hostname not in allowed_hosts:
            return secure_response(
                JSONResponse({"detail": "host denied"}, status_code=400),
                request,
            )
        local_admin = not private_exposure or (
            is_loopback_client(request) and hostname in {"127.0.0.1", "localhost", "::1"}
        )
        request.state.local_admin = local_admin
        request.state.paired_device = None
        if private_exposure:
            if not local_admin and not is_effective_https(request):
                return secure_response(
                    JSONResponse(
                        {"detail": "private console requires HTTPS"},
                        status_code=426,
                        headers={"Upgrade": "TLS/1.2"},
                    ),
                    request,
                )
            try:
                paired_device = pairing_store.validate_token(request.cookies.get(PAIRING_COOKIE))
            except PairingStateError:
                return secure_response(
                    JSONResponse(
                        {"detail": "device pairing state unavailable"},
                        status_code=503,
                    ),
                    request,
                )
            request.state.paired_device = paired_device
            if (
                not local_admin
                and paired_device is None
                and not is_public_pairing_path(request.url.path)
            ):
                if request.url.path.startswith("/api/"):
                    return secure_response(
                        JSONResponse(
                            {
                                "detail": "device pairing required",
                                "code": "pairing_required",
                            },
                            status_code=401,
                        ),
                        request,
                    )
                return secure_response(RedirectResponse("/pair", status_code=303), request)
            if request.url.path == "/pair" and (local_admin or paired_device is not None):
                return secure_response(RedirectResponse("/", status_code=303), request)
        if request.url.path.startswith("/api/") and request.method not in {
            "GET",
            "HEAD",
            "OPTIONS",
        }:
            origin = request.headers.get("origin")
            allowed_origins = local_origins if local_admin else public_origins
            if origin is not None and origin not in allowed_origins:
                return secure_response(
                    JSONResponse(
                        {"detail": "origin denied", "code": "origin_denied"},
                        status_code=403,
                    ),
                    request,
                )
            is_pair_claim = request.url.path == "/api/v1/pairing/claim"
            if private_exposure and not local_admin and origin not in allowed_origins:
                return secure_response(
                    JSONResponse({"detail": "origin required"}, status_code=403),
                    request,
                )
            if not is_pair_claim and request.headers.get("x-qd-csrf") != csrf_token:
                return secure_response(
                    JSONResponse({"detail": "csrf token required"}, status_code=403),
                    request,
                )
            is_library_upload = (
                request.method == "PUT"
                and request.url.path.startswith("/api/v1/library/imports/")
                and "/files/" in request.url.path
                and request.headers.get("content-type", "").startswith(
                    "application/octet-stream"
                )
            )
            if (
                not is_library_upload
                and not request.headers.get("content-type", "").startswith(
                    "application/json"
                )
            ):
                return secure_response(
                    JSONResponse({"detail": "application/json required"}, status_code=415),
                    request,
                )
        response: Response = await call_next(request)
        return secure_response(response, request)

    @app.exception_handler(PlanNotFound)
    async def not_found(_: Request, exc: PlanNotFound) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(BlueprintNotFound)
    async def blueprint_not_found(_: Request, exc: BlueprintNotFound) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(TaskTemplateNotFound)
    async def task_template_not_found(_: Request, exc: TaskTemplateNotFound) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(WorkspaceMemoryNotFound)
    async def workspace_memory_not_found(_: Request, exc: WorkspaceMemoryNotFound) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(ConsoleConflict)
    async def conflict(_: Request, exc: ConsoleConflict) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(ConsoleUnavailable)
    async def unavailable(_: Request, exc: ConsoleUnavailable) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.exception_handler(RuntimeArtifactNotFound)
    async def runtime_artifact_not_found(_: Request, exc: RuntimeArtifactNotFound) -> JSONResponse:
        return JSONResponse(
            {"detail": str(exc), "code": "runtime_artifact_not_found"},
            status_code=404,
        )

    @app.exception_handler(RuntimeArtifactPreviewError)
    async def runtime_artifact_preview_error(
        _: Request, exc: RuntimeArtifactPreviewError
    ) -> JSONResponse:
        return JSONResponse(
            {"detail": str(exc), "code": "runtime_artifact_preview_unavailable"},
            status_code=422,
        )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "exposure": settings.console.exposure}

    @app.get("/api/v1/pairing/status")
    async def pairing_status(request: Request) -> dict:
        paired = request.state.paired_device is not None
        return {
            "exposure": settings.console.exposure,
            "pairing_required": private_exposure and not request.state.local_admin and not paired,
            "paired": paired,
            "can_manage_devices": bool(request.state.local_admin or paired),
            "public_url": console_public_url(settings.console),
        }

    @app.post("/api/v1/pairing/claim")
    async def claim_pairing(body: PairingClaimRequest) -> Response:
        try:
            claim = await run_in_threadpool(pairing_store.claim, body.code, body.device_name)
        except InvalidPairingCode as exc:
            return JSONResponse({"detail": str(exc)}, status_code=403)
        except PairingLocked as exc:
            return JSONResponse(
                {"detail": str(exc)},
                status_code=429,
                headers={"Retry-After": "60"},
            )
        except PairingStateError:
            return JSONResponse({"detail": "device pairing unavailable"}, status_code=503)
        response = JSONResponse(
            {
                "paired": True,
                "device_id": claim.device_id,
                "expires_at": claim.expires_at.isoformat(),
            }
        )
        response.set_cookie(
            PAIRING_COOKIE,
            claim.token,
            max_age=settings.console.device_session_days * 86400,
            expires=claim.expires_at,
            secure=True,
            httponly=True,
            samesite="strict",
            path="/",
        )
        return response

    @app.get("/api/v1/pairing/devices")
    async def paired_devices(request: Request) -> list[dict[str, str]]:
        if not (request.state.local_admin or request.state.paired_device is not None):
            raise HTTPException(status_code=403, detail="device management denied")
        devices = await run_in_threadpool(pairing_store.list_devices)
        return [device.public_dict() for device in devices]

    @app.post("/api/v1/pairing/invitations", status_code=status.HTTP_201_CREATED)
    async def create_pairing_invitation(
        request: Request,
        body: PairingMutationRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del body, x_qd_csrf
        if not private_exposure:
            raise HTTPException(status_code=409, detail="private console exposure is disabled")
        if not (request.state.local_admin or request.state.paired_device is not None):
            raise HTTPException(status_code=403, detail="device management denied")
        invitation = await run_in_threadpool(pairing_store.create_invitation)
        return {
            "invitation_id": invitation.invitation_id,
            "code": invitation.code,
            "expires_at": invitation.expires_at.isoformat(),
            "public_url": console_public_url(settings.console),
        }

    @app.post("/api/v1/pairing/devices/{device_id}/revoke")
    async def revoke_paired_device(
        device_id: str,
        request: Request,
        body: PairingMutationRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> Response:
        del body, x_qd_csrf
        if not (request.state.local_admin or request.state.paired_device is not None):
            raise HTTPException(status_code=403, detail="device management denied")
        revoked = await run_in_threadpool(pairing_store.revoke, device_id)
        if not revoked:
            raise HTTPException(status_code=404, detail="paired device not found")
        response = JSONResponse({"device_id": device_id, "revoked": True})
        current = request.state.paired_device
        if current is not None and current.device_id == device_id:
            response.delete_cookie(PAIRING_COOKIE, path="/", secure=True, httponly=True)
        return response

    @app.post("/api/v1/pairing/unpair")
    async def unpair_current_device(
        request: Request,
        body: PairingMutationRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> Response:
        del body, x_qd_csrf
        revoked = await run_in_threadpool(
            pairing_store.revoke_token,
            request.cookies.get(PAIRING_COOKIE),
        )
        response = JSONResponse({"unpaired": revoked})
        response.delete_cookie(PAIRING_COOKIE, path="/", secure=True, httponly=True)
        return response

    @app.get("/api/v1/bootstrap")
    async def bootstrap(request: Request) -> dict:
        payload = await run_in_threadpool(service.dashboard)
        payload["csrf_token"] = csrf_token
        payload["console_access"] = {
            "exposure": settings.console.exposure,
            "public_url": console_public_url(settings.console),
            "paired": request.state.paired_device is not None,
            "can_manage_devices": bool(
                request.state.local_admin or request.state.paired_device is not None
            ),
        }
        return payload

    @app.get("/api/v1/onboarding")
    async def onboarding() -> dict:
        snapshot = await run_in_threadpool(service.onboarding_status)
        return snapshot.model_dump(mode="json")

    @app.get("/api/v1/works/{work_id}/recovery")
    async def work_recovery(work_id: str) -> dict:
        snapshot = await run_in_threadpool(service.recovery_status, work_id)
        return snapshot.model_dump(mode="json")

    @app.post("/api/v1/works/{work_id}/recovery/check")
    async def check_work_recovery(
        work_id: str,
        body: RecoveryCheckRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del body, x_qd_csrf
        snapshot = await run_in_threadpool(service.check_recovery, work_id)
        return snapshot.model_dump(mode="json")

    @app.post("/api/v1/works/{work_id}/recovery/decision")
    async def decide_work_recovery(
        work_id: str,
        body: RecoveryDecisionRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        snapshot, repair_work = await run_in_threadpool(
            service.decide_recovery,
            work_id,
            body,
        )
        return {
            "recovery": snapshot.model_dump(mode="json"),
            "repair_work": repair_work.model_dump(mode="json"),
        }

    @app.post("/api/v1/desktop/drain")
    async def desktop_drain(
        body: DesktopDrainRequest,
        x_opswitness_desktop_instance: str = Header(
            alias="X-OpsWitness-Desktop-Instance",
            min_length=8,
            max_length=128,
        ),
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        return await run_in_threadpool(
            service.desktop_drain,
            x_opswitness_desktop_instance,
            body.action,
        )

    @app.post("/api/v1/onboarding/migration")
    async def select_onboarding_migration(
        body: OnboardingMigrationRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        snapshot = await run_in_threadpool(service.select_onboarding_migration, body)
        return snapshot.model_dump(mode="json")

    @app.post("/api/v1/onboarding/provider")
    async def select_onboarding_provider(
        body: OnboardingProviderRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        snapshot = await run_in_threadpool(service.select_onboarding_provider, body)
        return snapshot.model_dump(mode="json")

    @app.post("/api/v1/onboarding/first-work", status_code=status.HTTP_201_CREATED)
    async def create_first_onboarding_work(
        body: OnboardingFirstWorkRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        snapshot, record = await run_in_threadpool(
            service.create_first_onboarding_work,
            body,
        )
        return {
            "onboarding": snapshot.model_dump(mode="json"),
            "plan": record.model_dump(mode="json"),
        }

    @app.post("/api/v1/works/{work_id}/artifact-signoff")
    async def signoff_onboarding_artifacts(
        work_id: str,
        body: ArtifactSignoffRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        snapshot = await run_in_threadpool(
            service.signoff_onboarding_artifacts,
            work_id,
            body,
        )
        return snapshot.model_dump(mode="json")

    @app.get("/api/v1/plans")
    async def plans() -> list[dict]:
        return [row.model_dump(mode="json") for row in await run_in_threadpool(service.list_plans)]

    @app.get("/api/v1/project-library", response_model=list[ProjectLibraryItem])
    async def project_library(
        query: str = "",
        tag: str = "",
        file_type: str = "",
        work_id: str = "",
    ) -> list[dict]:
        return await run_in_threadpool(
            service.list_project_library,
            query=query[:200],
            tag=tag[:40],
            file_type=file_type[:100],
            work_id=work_id[:64],
        )

    @app.get(
        "/api/v1/project-library/{asset_id}",
        response_model=ProjectLibraryItemPreview,
    )
    async def project_library_item(asset_id: str) -> dict:
        return await run_in_threadpool(service.get_project_library_item, asset_id)

    @app.patch(
        "/api/v1/project-library/{asset_id}",
        response_model=ProjectLibraryItemPreview,
    )
    async def update_project_library_item(
        asset_id: str,
        body: ProjectLibraryMetadataUpdate,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        return await run_in_threadpool(
            service.update_project_library_metadata,
            asset_id,
            body,
        )

    @app.get("/api/v1/project-library/{asset_id}/content")
    async def project_library_content(asset_id: str) -> Response:
        item = await run_in_threadpool(service.get_project_library_content, asset_id)
        return Response(
            content=item["content"],
            media_type=item["mime"],
            headers={
                "Content-Disposition": (
                    f"{item['disposition']}; filename*=UTF-8''{quote(item['name'], safe='')}"
                ),
                "X-OpsWitness-Artifact-SHA256": item["sha256"],
            },
        )

    @app.get("/api/v1/library/collections")
    async def library_collections() -> list[dict]:
        rows = await run_in_threadpool(service.list_library_collections)
        return [row.model_dump(mode="json") for row in rows]

    @app.post("/api/v1/library/collections", status_code=status.HTTP_201_CREATED)
    async def create_library_collection(
        body: LibraryCollectionCreateV1,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        row = await run_in_threadpool(service.create_library_collection, body)
        return row.model_dump(mode="json")

    @app.post(
        "/api/v1/library/collections/{collection_id}/revisions",
        status_code=status.HTTP_201_CREATED,
    )
    async def revise_library_collection(
        collection_id: str,
        body: LibraryCollectionRevisionRequestV1,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        row = await run_in_threadpool(
            service.revise_library_collection,
            collection_id,
            body,
        )
        return row.model_dump(mode="json")

    @app.post("/api/v1/library/imports", status_code=status.HTTP_201_CREATED)
    async def create_library_import(
        body: LibraryImportCreateRequestV1,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        row = await run_in_threadpool(service.create_library_import, body)
        return row.model_dump(mode="json")

    @app.put("/api/v1/library/imports/{import_id}/files/{entry_id}")
    async def upload_library_import_entry(
        import_id: str,
        entry_id: str,
        request: Request,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        row = await service.upload_library_import_entry(
            import_id,
            entry_id,
            request.stream(),
        )
        return row.model_dump(mode="json")

    @app.get("/api/v1/library/imports/{import_id}")
    async def get_library_import(import_id: str) -> dict:
        row = await run_in_threadpool(service.get_library_import, import_id)
        return row.model_dump(mode="json")

    @app.post("/api/v1/library/imports/{import_id}/commit")
    async def commit_library_import(
        import_id: str,
        body: LibraryImportCommitRequestV1,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        row = await run_in_threadpool(
            service.commit_library_import,
            import_id,
            body,
        )
        return row.model_dump(mode="json")

    @app.delete("/api/v1/library/imports/{import_id}")
    async def cancel_library_import(
        import_id: str,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        row = await run_in_threadpool(service.cancel_library_import, import_id)
        return row.model_dump(mode="json")

    @app.get("/api/v1/library/documents")
    async def library_documents(
        collection_id: str = "",
        include_history: bool = False,
    ) -> list[dict]:
        rows = await run_in_threadpool(
            service.list_library_documents,
            collection_id=collection_id,
            include_history=include_history,
        )
        return [row.model_dump(mode="json") for row in rows]

    @app.get("/api/v1/library/documents/{version_id}")
    async def library_document(version_id: str) -> dict:
        row = await run_in_threadpool(service.get_library_document, version_id)
        return row.model_dump(mode="json")

    @app.get("/api/v1/library/documents/{version_id}/content")
    async def library_document_content(version_id: str) -> Response:
        item = await run_in_threadpool(
            service.get_library_document_content,
            version_id,
        )
        return Response(
            content=item["content"],
            media_type=item["mime"],
            headers={
                "Content-Disposition": (
                    f"attachment; filename*=UTF-8''{quote(item['name'], safe='')}"
                ),
                "X-OpsWitness-Library-SHA256": item["sha256"],
            },
        )

    @app.patch("/api/v1/library/documents/{version_id}")
    async def update_library_document(
        version_id: str,
        body: LibraryDocumentMetadataUpdateV1,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        row = await run_in_threadpool(
            service.update_library_document_metadata,
            version_id,
            body,
        )
        return row.model_dump(mode="json")

    @app.delete("/api/v1/library/documents/{version_id}")
    async def tombstone_library_document(
        version_id: str,
        body: LibraryDocumentMetadataUpdateV1,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        row = await run_in_threadpool(
            service.tombstone_library_document,
            version_id,
            body,
        )
        return row.model_dump(mode="json")

    @app.post("/api/v1/library/card-jobs", status_code=status.HTTP_202_ACCEPTED)
    async def create_library_card_job(
        body: LibraryCardJobRequestV1,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        row = await run_in_threadpool(service.create_library_card_job, body)
        return row.model_dump(mode="json")

    @app.get("/api/v1/library/card-jobs/{job_id}")
    async def get_library_card_job(job_id: str) -> dict:
        row = await run_in_threadpool(service.get_library_card_job, job_id)
        return row.model_dump(mode="json")

    @app.get("/api/v1/library/cards")
    async def library_cards(
        collection_id: str = "",
        state: str = "",
    ) -> list[dict]:
        rows = await run_in_threadpool(
            service.list_library_cards,
            collection_id=collection_id,
            state=state,
        )
        return [row.model_dump(mode="json") for row in rows]

    async def decide_library_card(
        version_id: str,
        action: Literal["approve", "dismiss", "revoke"],
        body: LibraryCardDecisionRequestV1,
    ) -> dict:
        row = await run_in_threadpool(
            service.decide_library_card,
            version_id,
            action,
            body,
        )
        return row.model_dump(mode="json")

    @app.post("/api/v1/library/cards/{version_id}/approve")
    async def approve_library_card(
        version_id: str,
        body: LibraryCardDecisionRequestV1,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        return await decide_library_card(version_id, "approve", body)

    @app.post("/api/v1/library/cards/{version_id}/dismiss")
    async def dismiss_library_card(
        version_id: str,
        body: LibraryCardDecisionRequestV1,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        return await decide_library_card(version_id, "dismiss", body)

    @app.post("/api/v1/library/cards/{version_id}/revoke")
    async def revoke_library_card(
        version_id: str,
        body: LibraryCardDecisionRequestV1,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        return await decide_library_card(version_id, "revoke", body)

    @app.post("/api/v1/library/search")
    async def library_search(
        body: LibrarySearchRequestV1,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        result = await run_in_threadpool(service.search_library, body)
        return result.model_dump(mode="json")

    @app.get("/api/v1/library/index/status")
    async def library_index_status() -> dict:
        row = await run_in_threadpool(service.library_index_status)
        return row.model_dump(mode="json")

    @app.post("/api/v1/library/index/rebuild", status_code=status.HTTP_202_ACCEPTED)
    async def rebuild_library_index(
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        row = await run_in_threadpool(service.rebuild_library_index)
        return row.model_dump(mode="json")

    @app.get("/api/v1/library/semantic-model/status")
    async def library_semantic_model_status() -> dict:
        row = await run_in_threadpool(service.library_semantic_model_status)
        return row.model_dump(mode="json")

    @app.post(
        "/api/v1/library/semantic-model/download",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def download_library_semantic_model(
        body: LibrarySemanticModelDownloadRequestV1,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del body, x_qd_csrf
        row = await run_in_threadpool(
            service.request_library_semantic_model_download
        )
        return row.model_dump(mode="json")

    @app.post("/api/v1/plans/from-library", status_code=status.HTTP_202_ACCEPTED)
    async def create_plan_from_library(
        body: LibraryPlanRequestV1,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        record = await run_in_threadpool(service.request_plan_from_library, body)
        return record.model_dump(mode="json")

    @app.post("/api/v1/library/exports/preview")
    async def preview_library_export(
        body: LibraryH5ExportPreviewRequestV1,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        return await run_in_threadpool(
            service.preview_library_export,
            body.collection_id,
            body.expected_collection_revision,
            body.policy,
        )

    @app.post("/api/v1/library/exports", status_code=status.HTTP_201_CREATED)
    async def create_library_export(
        body: LibraryH5ExportRequestV1,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        row = await run_in_threadpool(service.create_library_export, body)
        return row.model_dump(mode="json")

    @app.get("/api/v1/library/exports/{export_id}/download")
    async def download_library_export(export_id: str) -> FileResponse:
        item = await run_in_threadpool(service.get_library_export_download, export_id)
        row = item["record"]
        return FileResponse(
            item["path"],
            media_type="application/zip",
            filename=f"opswitness-knowledge-{export_id}.zip",
            headers={"X-OpsWitness-Export-SHA256": row.output_sha256},
        )

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

    @app.post(
        "/api/v1/plans/{plan_id}/agent-graph/revisions",
        status_code=status.HTTP_201_CREATED,
    )
    async def revise_plan_agent_graph(
        plan_id: str,
        body: AgentGraphRevisionRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        record = await run_in_threadpool(service.revise_plan_agent_graph, plan_id, body)
        return record.model_dump(mode="json")

    @app.post("/api/v1/plans/{plan_id}/agent-contract/preview")
    async def preview_plan_agent_contract(
        plan_id: str,
        body: AgentContractPreviewRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        preview = await run_in_threadpool(
            service.preview_agent_contract,
            plan_id,
            body,
        )
        return preview.model_dump(mode="json")

    @app.post(
        "/api/v1/plans/{plan_id}/agent-contract/revisions",
        status_code=status.HTTP_201_CREATED,
    )
    async def revise_plan_agent_contract(
        plan_id: str,
        body: AgentContractRevisionRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        record = await run_in_threadpool(
            service.revise_plan_agent_contract,
            plan_id,
            body,
        )
        return record.model_dump(mode="json")

    @app.get("/api/v1/plans/{plan_id}/agent-contract/versions")
    async def list_plan_agent_contract_versions(plan_id: str) -> list[dict]:
        return await run_in_threadpool(service.list_agent_contract_versions, plan_id)

    @app.get("/api/v1/plans/{child_plan_id}/agent-contract/diff")
    async def diff_plan_agent_contract(
        child_plan_id: str,
        base_plan_id: str,
    ) -> list[dict]:
        rows = await run_in_threadpool(
            service.diff_agent_contract_versions,
            child_plan_id,
            base_plan_id,
        )
        return [row.model_dump(mode="json") for row in rows]

    @app.post(
        "/api/v1/plans/{plan_id}/runtimes",
        status_code=status.HTTP_201_CREATED,
    )
    async def revise_plan_runtimes(
        plan_id: str,
        body: RuntimeRevisionRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        record = await run_in_threadpool(service.revise_plan_runtimes, plan_id, body)
        return record.model_dump(mode="json")

    @app.post(
        "/api/v1/plans/{plan_id}/execution-profile",
        status_code=status.HTTP_201_CREATED,
    )
    async def revise_plan_execution_profile(
        plan_id: str,
        body: ExecutionProfileRevisionRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        record = await run_in_threadpool(
            service.revise_plan_execution_profile,
            plan_id,
            body,
        )
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

    @app.post("/api/v1/plans/{plan_id}/rerun", status_code=status.HTTP_201_CREATED)
    async def prepare_plan_rerun(
        plan_id: str,
        body: RerunPlanRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        record = await run_in_threadpool(service.prepare_plan_rerun, plan_id, body)
        return record.model_dump(mode="json")

    @app.post("/api/v1/plans/{plan_id}/continue", status_code=status.HTTP_202_ACCEPTED)
    async def continue_plan_run(
        plan_id: str,
        body: ContinueRunRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        record = await run_in_threadpool(service.continue_plan_run, plan_id, body)
        return record.model_dump(mode="json")

    @app.post("/api/v1/plans/{plan_id}/fork", status_code=status.HTTP_201_CREATED)
    async def fork_plan(
        plan_id: str,
        body: ForkPlanRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        record = await run_in_threadpool(service.fork_plan, plan_id, body)
        return record.model_dump(mode="json")

    @app.post("/api/v1/plans/{plan_id}/control", status_code=status.HTTP_202_ACCEPTED)
    async def control_execution(
        plan_id: str,
        body: ExecutionControlRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        record = await run_in_threadpool(service.control_execution, plan_id, body)
        return record.model_dump(mode="json")

    @app.post(
        "/api/v1/plans/{plan_id}/approval-mode",
        status_code=status.HTTP_200_OK,
    )
    async def change_execution_approval_mode(
        plan_id: str,
        body: ExecutionApprovalModeRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        record = await run_in_threadpool(
            service.change_execution_approval_mode,
            plan_id,
            body,
        )
        return record.model_dump(mode="json")

    @app.post("/api/v1/plans/{plan_id}/input-requests/{request_id}/answer")
    async def answer_runtime_input(
        plan_id: str,
        request_id: str,
        body: RuntimeInputAnswerRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        record = await run_in_threadpool(
            service.answer_runtime_input,
            plan_id,
            request_id,
            body,
        )
        return record.model_dump(mode="json")

    @app.get("/api/v1/plans/{plan_id}/input-requests/{request_id}/artifacts")
    async def runtime_input_artifacts(plan_id: str, request_id: str) -> list[dict]:
        return await run_in_threadpool(service.list_runtime_input_artifacts, plan_id, request_id)

    @app.get("/api/v1/plans/{plan_id}/input-requests/{request_id}/artifacts/{artifact_name}")
    async def runtime_input_artifact(
        plan_id: str,
        request_id: str,
        artifact_name: str,
    ) -> dict:
        return await run_in_threadpool(
            service.get_runtime_input_artifact,
            plan_id,
            request_id,
            artifact_name,
        )

    @app.get("/api/v1/plans/{plan_id}/artifacts")
    async def plan_artifacts(plan_id: str) -> list[dict]:
        return await run_in_threadpool(service.list_plan_artifacts, plan_id)

    @app.get("/api/v1/plans/{plan_id}/artifacts/{artifact_name}")
    async def plan_artifact(plan_id: str, artifact_name: str) -> dict:
        return await run_in_threadpool(
            service.get_plan_artifact,
            plan_id,
            artifact_name,
        )

    @app.get("/api/v1/plans/{plan_id}/artifacts/{artifact_name}/content")
    async def plan_artifact_content(plan_id: str, artifact_name: str) -> Response:
        artifact = await run_in_threadpool(
            service.get_plan_artifact_content,
            plan_id,
            artifact_name,
        )
        return Response(
            content=artifact["content"],
            media_type=artifact["mime"],
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": (
                    f'{artifact["disposition"]}; filename="{artifact["name"]}"'
                ),
                "X-Content-Type-Options": "nosniff",
                "X-OpsWitness-Artifact-SHA256": artifact["sha256"],
            },
        )

    @app.delete("/api/v1/plans/{plan_id}")
    async def delete_plan(
        plan_id: str,
        body: DeletePlanRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        return await run_in_threadpool(service.delete_plan, plan_id, body)

    @app.delete("/api/v1/plans/{plan_id}/run-data")
    async def erase_run_data(
        plan_id: str,
        body: EraseRunRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        return await run_in_threadpool(service.erase_run_data, plan_id, body)

    @app.get("/api/v1/task-templates")
    async def task_templates(include_archived: bool = False) -> list[dict]:
        rows = await run_in_threadpool(
            service.list_task_templates, include_archived=include_archived
        )
        return [row.model_dump(mode="json") for row in rows]

    @app.post("/api/v1/task-templates", status_code=status.HTTP_201_CREATED)
    async def save_task_template(
        body: TaskTemplateSaveRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        template = await run_in_threadpool(service.save_task_template, body)
        return template.model_dump(mode="json")

    @app.post(
        "/api/v1/plans/{plan_id}/task-template",
        status_code=status.HTTP_201_CREATED,
    )
    async def save_task_template_from_plan(
        plan_id: str,
        body: TaskTemplateFromPlanRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        template = await run_in_threadpool(
            service.save_task_template_from_plan,
            plan_id,
            body,
        )
        return template.model_dump(mode="json")

    @app.post("/api/v1/task-templates/{template_id}/archive")
    async def archive_task_template(
        template_id: str,
        body: TaskTemplateArchiveRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        template = await run_in_threadpool(
            service.archive_task_template,
            template_id,
            body,
        )
        return template.model_dump(mode="json")

    @app.get("/api/v1/team-blueprints")
    async def team_blueprints(include_archived: bool = False) -> list[dict]:
        rows = await run_in_threadpool(
            service.list_team_blueprints, include_archived=include_archived
        )
        return [row.model_dump(mode="json") for row in rows]

    @app.post("/api/v1/team-blueprints", status_code=status.HTTP_201_CREATED)
    async def save_team_blueprint(
        body: TeamBlueprintSaveRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        blueprint = await run_in_threadpool(service.save_team_blueprint, body)
        return blueprint.model_dump(mode="json")

    @app.get("/api/v1/repeatable-works")
    async def repeatable_works() -> list[dict]:
        rows = await run_in_threadpool(service.list_repeatable_works)
        return [row.model_dump(mode="json") for row in rows]

    @app.get("/api/v1/workspace-conversations")
    async def workspace_conversations() -> list[dict]:
        rows = await run_in_threadpool(service.list_workspace_conversations)
        return [row.model_dump(mode="json") for row in rows]

    @app.get("/api/v1/workspace-memory")
    async def workspace_memories(
        query: str = "",
        include_history: bool = True,
    ) -> list[dict]:
        rows = await run_in_threadpool(
            service.list_workspace_memories,
            query=query,
            include_history=include_history,
        )
        return [row.model_dump(mode="json") for row in rows]

    @app.get("/api/v1/workspace-memory/{version_id}")
    async def workspace_memory(version_id: str) -> dict:
        row = await run_in_threadpool(service.get_workspace_memory, version_id)
        return row.model_dump(mode="json")

    @app.post("/api/v1/workspace-memory/candidates", status_code=status.HTTP_201_CREATED)
    async def create_workspace_memory_candidate(
        body: WorkspaceMemoryCandidateRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        try:
            row = await run_in_threadpool(service.create_workspace_memory_candidate, body)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return row.model_dump(mode="json")

    @app.post(
        "/api/v1/plans/{plan_id}/memory-candidates",
        status_code=status.HTTP_201_CREATED,
    )
    async def propose_process_memory(
        plan_id: str,
        body: ProcessMemoryProposalRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        row = await run_in_threadpool(service.propose_process_memory, plan_id, body)
        return row.model_dump(mode="json")

    @app.post("/api/v1/workspace-memory/{version_id}/approve")
    async def approve_workspace_memory(
        version_id: str,
        body: WorkspaceMemoryDecisionRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        row = await run_in_threadpool(service.approve_workspace_memory, version_id, body)
        return row.model_dump(mode="json")

    @app.post("/api/v1/workspace-memory/{version_id}/dismiss")
    async def dismiss_workspace_memory(
        version_id: str,
        body: WorkspaceMemoryDecisionRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        row = await run_in_threadpool(service.dismiss_workspace_memory, version_id, body)
        return row.model_dump(mode="json")

    @app.post("/api/v1/workspace-memory/{version_id}/revoke")
    async def revoke_workspace_memory(
        version_id: str,
        body: WorkspaceMemoryDecisionRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        row = await run_in_threadpool(service.revoke_workspace_memory, version_id, body)
        return row.model_dump(mode="json")

    @app.post("/api/v1/workspace-memory/{version_id}/rollback")
    async def rollback_workspace_memory(
        version_id: str,
        body: WorkspaceMemoryRollbackRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        row = await run_in_threadpool(service.rollback_workspace_memory, version_id, body)
        return row.model_dump(mode="json")

    @app.post("/api/v1/team-blueprints/{blueprint_id}/archive")
    async def archive_team_blueprint(
        blueprint_id: str,
        body: TeamBlueprintArchiveRequest,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        blueprint = await run_in_threadpool(
            service.archive_team_blueprint,
            blueprint_id,
            body,
        )
        return blueprint.model_dump(mode="json")

    @app.get("/api/v1/providers")
    async def providers() -> dict:
        return await run_in_threadpool(service.provider_statuses)

    @app.post("/api/v1/providers/{provider}/connect", status_code=status.HTTP_202_ACCEPTED)
    async def connect_provider(
        provider: Literal["openai", "anthropic", "deepseek", "xai", "ollama", "lmstudio"],
        request: Request,
        x_qd_csrf: str = Header(alias="X-QD-CSRF"),
    ) -> dict:
        del x_qd_csrf
        try:
            body = ProviderConnectionRequest.model_validate(await request.json())
        except (ValidationError, ValueError):
            raise ConsoleConflict("invalid provider connection request") from None
        job = await run_in_threadpool(service.request_provider_connection, provider, body)
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

    @app.get("/pair", include_in_schema=False)
    async def pairing_page() -> Response:
        page = static_dir / "pair.html"
        if page.exists():
            return FileResponse(page)
        return JSONResponse(
            {"detail": "pairing frontend is not built; run npm run build in console-ui"},
            status_code=503,
        )

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
