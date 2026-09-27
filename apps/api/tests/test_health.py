from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from voker_voice_api.database import get_db
from voker_voice_api.main import app


def test_health() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_dashboard_origins_allow_session_credentials() -> None:
    response = TestClient(app).get(
        "/health",
        headers={"Origin": "http://127.0.0.1:5173"},
    )

    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_readiness_reports_durable_queue_backlog() -> None:
    db = MagicMock()
    db.scalar.side_effect = [3, 2, 1]
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "pending_jobs": 3,
        "pending_capture_sessions": 2,
        "incomplete_capture_sessions": 1,
    }
