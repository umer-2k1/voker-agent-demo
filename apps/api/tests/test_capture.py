from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from voker_voice_api.capture import accept_event_batch, project_pending_captures
from voker_voice_api.database import Base
from voker_voice_api.ingestion import IngestContext
from voker_voice_api.models import (
    AnalysisRun,
    Environment,
    Job,
    Organization,
    Project,
    SessionCapture,
)
from voker_voice_api.models import Session as VoiceSession


def database() -> tuple[Session, IngestContext]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    organization = Organization(name="Capture Test")
    db.add(organization)
    db.flush()
    project = Project(organization_id=organization.id, name="Voice", slug="capture-test")
    db.add(project)
    db.flush()
    environment = Environment(
        project_id=project.id,
        name="Test",
        slug="test",
        kind="development",
    )
    db.add(environment)
    db.flush()
    return db, IngestContext(
        resolved_project_id=project.id,
        resolved_environment_id=environment.id,
    )


def raw_event(sequence: int, event_type: str, *, event_id: str | None = None) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "event_id": event_id or f"evt_{sequence}",
        "event_type": event_type,
        "occurred_at": (
            datetime(2026, 9, 27, 13, 40, tzinfo=UTC) + timedelta(seconds=sequence)
        ).isoformat(),
        "sequence": sequence,
        "external_session_id": "capture-call",
        "trace_id": "trace-capture",
        "source": {"integration": "livekit"},
        "status": "ok",
        "attributes": {},
    }


def test_terminal_event_with_gap_is_durable_but_does_not_start_analysis() -> None:
    db, context = database()

    response = accept_event_batch(
        db,
        context,
        [raw_event(1, "session.started"), raw_event(3, "session.ended")],
    )
    db.commit()
    projected = project_pending_captures(db, worker_id="test-worker")
    db.commit()

    capture = db.scalar(select(SessionCapture))
    session = db.scalar(select(VoiceSession))
    assert response.accepted == 2
    assert projected == 1
    assert capture is not None
    assert capture.state == "incomplete"
    assert capture.raw_event_count == 2
    assert capture.generation == 2
    assert capture.highest_contiguous_sequence == 1
    assert capture.expected_last_sequence == 3
    assert capture.missing_ranges == [[2, 2]]
    assert session is not None
    assert session.status == "completed"
    assert list(db.scalars(select(Job))) == []
    assert list(db.scalars(select(AnalysisRun))) == []


def test_late_event_closes_gap_and_schedules_analysis_exactly_once() -> None:
    db, context = database()
    accept_event_batch(
        db,
        context,
        [raw_event(1, "session.started"), raw_event(3, "session.ended")],
    )
    db.commit()
    project_pending_captures(db, worker_id="test-worker")
    db.commit()

    first = accept_event_batch(db, context, [raw_event(2, "user.message")])
    duplicate = accept_event_batch(
        db,
        context,
        [raw_event(2, "user.message")],
    )
    db.commit()
    project_pending_captures(db, worker_id="test-worker")
    db.commit()
    project_pending_captures(db, worker_id="test-worker")
    db.commit()

    capture = db.scalar(select(SessionCapture))
    assert first.accepted == 1
    assert duplicate.duplicate == 1
    assert capture is not None
    assert capture.state == "complete"
    assert capture.highest_contiguous_sequence == 3
    assert capture.missing_ranges == []
    assert len(list(db.scalars(select(Job)))) == 2
    assert len(list(db.scalars(select(AnalysisRun)))) == 2


def test_sequence_collision_is_permanently_rejected_without_losing_original() -> None:
    db, context = database()
    original = raw_event(1, "session.started", event_id="evt_original")
    collision = raw_event(1, "user.message", event_id="evt_collision")

    first = accept_event_batch(db, context, [original])
    second = accept_event_batch(db, context, [collision])
    db.commit()

    assert first.accepted == 1
    assert second.rejected == 1
    assert second.items[0].status == "rejected_permanent"
    assert second.items[0].detail == "sequence is already occupied by another event"
    capture = db.scalar(select(SessionCapture))
    assert capture is not None
    assert capture.raw_event_count == 1
    assert capture.permanent_rejection_count == 1
