from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from voker_voice_api.config import get_settings
from voker_voice_api.database import get_db
from voker_voice_api.models import Job
from voker_voice_api.routers.dashboard import router as dashboard_router
from voker_voice_api.routers.ingest import router as ingest_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )
    app.include_router(ingest_router)
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
        except SQLAlchemyError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database is unavailable",
            ) from error
        return {"status": "ready", "pending_jobs": pending_jobs or 0}

    return app


app = create_app()
