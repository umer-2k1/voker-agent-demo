from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from voker_voice_api.database import get_db
from voker_voice_api.main import app


def test_health() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_reports_durable_queue_backlog() -> None:
    db = MagicMock()
    db.scalar.return_value = 3
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "pending_jobs": 3}
