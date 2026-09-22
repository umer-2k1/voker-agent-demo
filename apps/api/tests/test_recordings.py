from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from voker_voice_api.config import get_settings
from voker_voice_api.database import get_db
from voker_voice_api.main import app
from voker_voice_api.models import Recording
from voker_voice_api.recordings import cloudinary_playback_url
from voker_voice_api.routers.account import require_dashboard_user
from voker_voice_api.worker import expire_recordings


def test_expiring_recording_preserves_trace_but_revokes_asset_reference() -> None:
    recording = Recording(
        source="cloudinary", asset_reference="private/voice-call", status="available"
    )
    db = MagicMock()
    db.scalars.return_value = [recording]

    expired = expire_recordings(db, now=datetime.now(UTC))

    assert expired == 1
    assert recording.status == "expired"
    assert recording.asset_reference is None


def test_cloudinary_playback_url_is_authenticated_and_short_lived(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "cloudinary_cloud_name", "demo-cloud")
    monkeypatch.setattr(settings, "cloudinary_api_key", "test-key")
    monkeypatch.setattr(settings, "cloudinary_api_secret", "test-secret")
    recording = Recording(
        source="cloudinary",
        asset_reference="voker_voice/verification/cinematic_hit_317170",
        media_type="audio/mpeg",
    )

    url = cloudinary_playback_url(recording, settings)

    assert "api.cloudinary.com" in url
    assert "/video/download?" in url
    assert "type=authenticated" in url
    assert "format=mp3" in url
    assert "expires_at=" in url


def test_playback_redirects_only_available_cloudinary_recordings(monkeypatch) -> None:
    recording = Recording(source="cloudinary", asset_reference="private/call", status="available")
    db = MagicMock()
    project = MagicMock()
    project.id = "project-id"
    db.scalar.side_effect = [project, recording]
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_dashboard_user] = lambda: MagicMock()
    monkeypatch.setattr(
        "voker_voice_api.routers.dashboard.cloudinary_playback_url",
        lambda recording, settings: "https://example.test/private-audio",
    )
    try:
        session_id = uuid4()
        recording_id = uuid4()
        response = TestClient(app).get(
            f"/api/projects/voker-voice/sessions/{session_id}/recordings/{recording_id}/playback",
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 307
    assert response.headers["location"] == "https://example.test/private-audio"
