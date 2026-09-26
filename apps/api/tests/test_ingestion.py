import gzip
import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from voker_voice_api.database import Base, get_db
from voker_voice_api.auth import authenticate_ingest_key
from voker_voice_api.ingestion import IngestContext
from voker_voice_api.ingestion import ingest_batch, sse_payload
from voker_voice_api.main import app
from voker_voice_api.models import (
    AnalysisRun,
    APIKey,
    Environment,
    Job,
    Organization,
    Project,
    Recording,
)
from voker_voice_api.models import Session as VoiceSession
from voker_voice_api.schemas import CanonicalEvent
from voker_voice_api.security import generate_ingest_key


def raw_event(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_id": "evt-valid",
        "event_type": "llm.completed",
        "occurred_at": datetime.now(UTC).isoformat(),
        "external_session_id": "session-1",
        "trace_id": "trace-1",
        "status": "ok",
    }
    payload.update(overrides)
    return payload


def test_batch_keeps_valid_events_when_one_item_is_invalid(monkeypatch) -> None:
    db = MagicMock()
    context = MagicMock()
    monkeypatch.setattr("voker_voice_api.ingestion.persist_event", lambda *_: "accepted")

    result = ingest_batch(db, context, [raw_event(), {"event_id": "invalid"}])

    assert result.accepted == 1
    assert result.rejected == 1
    assert result.items[0].status == "accepted"
    assert result.items[1].status == "rejected"


def test_sse_payload_includes_trace_identity() -> None:
    event = CanonicalEvent.model_validate(raw_event())

    payload = sse_payload(event)

    assert "evt-valid" in payload
    assert "llm.completed" in payload


def test_event_batch_accepts_the_voker_api_key_header() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    organization = Organization(name="Batch Header")
    db.add(organization)
    db.flush()
    project = Project(organization_id=organization.id, name="Voice", slug="batch-header")
    db.add(project)
    db.flush()
    environment = Environment(
        project_id=project.id,
        name="Development",
        slug="development",
        kind="development",
    )
    db.add(environment)
    db.flush()
    generated = generate_ingest_key("test")
    db.add(
        APIKey(
            project_id=project.id,
            environment_id=environment.id,
            label="SDK exporter",
            prefix=generated.prefix,
            secret_hash=generated.secret_hash,
        )
    )
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        payload = {"schema_version": "1.0", "events": [raw_event()]}
        response = TestClient(app).post(
            "/v1/events/batch",
            content=gzip.compress(json.dumps(payload).encode()),
            headers={
                "Content-Encoding": "gzip",
                "Content-Type": "application/json",
                "X-Voker-Api-Key": generated.raw,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["accepted"] == 1
    db.close()


def test_ingest_authentication_does_not_lock_the_api_key_row_per_batch() -> None:
    """High-frequency telemetry must not mutate the shared API-key row."""

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = Session(engine)
    organization = Organization(name="No hot-row writes")
    db.add(organization)
    db.flush()
    project = Project(organization_id=organization.id, name="Voice", slug="no-hot-row")
    db.add(project)
    db.flush()
    environment = Environment(
        project_id=project.id, name="Development", slug="development", kind="development"
    )
    db.add(environment)
    db.flush()
    generated = generate_ingest_key("test")
    key = APIKey(
        project_id=project.id,
        environment_id=environment.id,
        label="Telemetry",
        prefix=generated.prefix,
        secret_hash=generated.secret_hash,
    )
    db.add(key)
    db.commit()

    context = authenticate_ingest_key(generated.raw, db)

    assert isinstance(context, IngestContext)
    assert key.last_used_at is None
    assert not db.is_modified(key)
    db.close()


def test_authenticated_session_routes_preserve_outcome_and_queue_completion_once() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    organization = Organization(name="Ingestion API")
    db.add(organization)
    db.flush()
    project = Project(organization_id=organization.id, name="Voice", slug="voice")
    db.add(project)
    db.flush()
    environment = Environment(
        project_id=project.id,
        name="Development",
        slug="development",
        kind="development",
    )
    db.add(environment)
    db.flush()
    generated = generate_ingest_key("test")
    db.add(
        APIKey(
            project_id=project.id,
            environment_id=environment.id,
            label="Acceptance",
            prefix=generated.prefix,
            secret_hash=generated.secret_hash,
        )
    )
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    headers = {"Authorization": f"Bearer {generated.raw}"}
    started_at = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
    try:
        client = TestClient(app)
        created = client.post(
            "/v1/sessions",
            headers=headers,
            json={
                "external_session_id": "call-1",
                "trace_id": "trace-1",
                "source": "livekit",
                "started_at": started_at.isoformat(),
                "metadata": {"deployment": "development"},
            },
        )
        assert created.status_code == 201
        updated = client.patch(
            "/v1/sessions/call-1",
            headers=headers,
            json={"outcome": "resolved", "outcome_source": "explicit"},
        )
        assert updated.status_code == 200
        recording = client.post(
            "/v1/recordings",
            headers=headers,
            json={
                "external_session_id": "call-1",
                "source": "livekit",
                "external_id": "egress-1",
                "status": "processing",
            },
        )
        assert recording.status_code == 201
        for _ in range(2):
            ended = client.post(
                "/v1/sessions/call-1/end",
                headers=headers,
                json={"ended_at": started_at.isoformat(), "status": "completed"},
            )
            assert ended.status_code == 200
    finally:
        app.dependency_overrides.clear()

    session = db.scalar(select(VoiceSession).where(VoiceSession.external_session_id == "call-1"))
    assert session is not None
    assert session.status == "completed"
    assert session.outcome == "resolved"
    assert session.outcome_source == "explicit"
    stored_recording = db.scalar(select(Recording))
    assert stored_recording is not None
    assert stored_recording.source == "livekit"
    assert stored_recording.status == "processing"
    assert db.scalar(select(func.count()).select_from(Job)) == 2
    assert set(db.scalars(select(AnalysisRun.prompt_version))) == {
        "deterministic-v2",
        "semantic-v3",
    }
    db.close()
