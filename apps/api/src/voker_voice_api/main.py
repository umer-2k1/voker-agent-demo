from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from voker_voice_api.config import get_settings
from voker_voice_api.routers.dashboard import router as dashboard_router
from voker_voice_api.routers.ingest import router as ingest_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(ingest_router)
    app.include_router(dashboard_router)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.app_env}

    return app


app = create_app()
