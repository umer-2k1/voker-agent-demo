from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from voker_voice_api.config import get_settings
from voker_voice_api.database import get_db
from voker_voice_api.mcp_server import create_mcp_app
from voker_voice_api.models import Job, SessionCapture
from voker_voice_api.routers.account import router as account_router
from voker_voice_api.routers.dashboard import router as dashboard_router
from voker_voice_api.routers.ingest import router as ingest_router


class MCPMount:
    """Give every API lifespan a fresh FastMCP session manager."""

    def __init__(self) -> None:
        self.app: Any | None = None
        self._lifespan: Any | None = None

    async def start(self) -> None:
        self.app = create_mcp_app()
        self._lifespan = self.app.router.lifespan_context(self.app)
        await self._lifespan.__aenter__()

    async def stop(self) -> None:
        if self._lifespan is not None:
            await self._lifespan.__aexit__(None, None, None)
        self._lifespan = None
        self.app = None

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if self.app is None:
            await send(
                {
                    "type": "http.response.start",
                    "status": 503,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b'{"detail":"MCP server is unavailable"}',
                }
            )
            return
        await self.app(scope, receive, send)


def create_app() -> FastAPI:
    settings = get_settings()
    mcp_mount = MCPMount()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await mcp_mount.start()
        try:
            yield
        finally:
            await mcp_mount.stop()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    if settings.session_secret:
        app.add_middleware(
            SessionMiddleware,
            secret_key=settings.session_secret,
            https_only=settings.app_env != "development",
            same_site="lax",
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )
    app.include_router(ingest_router)
    app.include_router(account_router)
    app.include_router(dashboard_router)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.app_env}

    @app.get("/health/ready", tags=["system"])
    def readiness(db: Session = Depends(get_db)) -> dict[str, int | str]:
        """Report database reachability and durable-queue backlog for operators."""

        try:
            db.execute(select(1))
            pending_jobs = db.scalar(
                select(func.count()).select_from(Job).where(Job.state.in_(("pending", "retry")))
            )
            pending_capture_sessions = db.scalar(
                select(func.count())
                .select_from(SessionCapture)
                .where(SessionCapture.projected_generation < SessionCapture.generation)
            )
            incomplete_capture_sessions = db.scalar(
                select(func.count())
                .select_from(SessionCapture)
                .where(SessionCapture.state == "incomplete")
            )
        except SQLAlchemyError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database is unavailable",
            ) from error
        return {
            "status": "ready",
            "pending_jobs": pending_jobs or 0,
            "pending_capture_sessions": pending_capture_sessions or 0,
            "incomplete_capture_sessions": incomplete_capture_sessions or 0,
        }

    # This catch-all mount must stay after API and health routes.
    app.mount("/", mcp_mount)
    return app


app = create_app()
