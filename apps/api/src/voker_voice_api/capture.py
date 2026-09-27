from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, insert, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from voker_voice_api.ingestion import (
    IngestContext,
    enqueue_completion_analysis,
    persist_event,
)
from voker_voice_api.models import RawEvent, SessionCapture
from voker_voice_api.models import Session as VoiceSession
from voker_voice_api.schemas import BatchItemResult, CanonicalEvent, EventBatchResponse
from voker_voice_api.session_logs import write_session_log


def _insert_do_nothing(
    db: Session,
    model: type[RawEvent] | type[SessionCapture],
    values: dict[str, Any],
    *,
    conflict_columns: list[str] | None,
) -> bool:
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        pg_statement = postgresql_insert(model).values(**values)
        result = db.execute(
            pg_statement.on_conflict_do_nothing(index_elements=conflict_columns)
            if conflict_columns
            else pg_statement.on_conflict_do_nothing()
        )
    elif dialect == "sqlite":
        sqlite_statement = sqlite_insert(model).values(**values)
        result = db.execute(
            sqlite_statement.on_conflict_do_nothing(index_elements=conflict_columns)
            if conflict_columns
            else sqlite_statement.on_conflict_do_nothing()
        )
    else:
        result = db.execute(insert(model).values(**values))
    assert isinstance(result, CursorResult)
    return bool(result.rowcount)


def _capture_for_event(
    db: Session, context: IngestContext, event: CanonicalEvent
) -> SessionCapture:
    _insert_do_nothing(
        db,
        SessionCapture,
        {
            "id": uuid.uuid4(),
            "project_id": context.project_id,
            "environment_id": context.environment_id,
            "external_session_id": event.external_session_id,
            "state": "receiving",
            "missing_ranges": [],
            "raw_event_count": 0,
            "projected_event_count": 0,
            "permanent_rejection_count": 0,
            "generation": 0,
            "projected_generation": 0,
            "last_received_at": datetime.now(UTC),
        },
        conflict_columns=["project_id", "environment_id", "external_session_id"],
    )
    capture = db.scalar(
        select(SessionCapture)
        .where(
            SessionCapture.project_id == context.project_id,
            SessionCapture.environment_id == context.environment_id,
            SessionCapture.external_session_id == event.external_session_id,
        )
        .with_for_update()
    )
    if capture is None:
        raise RuntimeError("capture state was not created")
    return capture


def _raw_event_values(
    context: IngestContext, event: CanonicalEvent
) -> dict[str, Any]:
    return {
        "id": uuid.uuid4(),
        "project_id": context.project_id,
        "environment_id": context.environment_id,
        "external_session_id": event.external_session_id,
        "event_id": event.event_id,
        "sequence": event.sequence,
        "event_type": event.event_type,
        "occurred_at": event.occurred_at,
        "payload": event.model_dump(mode="json"),
        "projection_attempts": 0,
    }


def _insert_raw_event_batch(
    db: Session,
    context: IngestContext,
    events: list[CanonicalEvent],
) -> set[str]:
    """Insert a replay batch in one round trip and return newly durable IDs."""

    if not events:
        return set()
    values = [_raw_event_values(context, event) for event in events]
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        pg_statement = (
            postgresql_insert(RawEvent)
            .values(values)
            .on_conflict_do_nothing()
            .returning(RawEvent.event_id)
        )
        return {str(event_id) for event_id in db.scalars(pg_statement)}
    elif dialect == "sqlite":
        sqlite_statement = (
            sqlite_insert(RawEvent)
            .values(values)
            .on_conflict_do_nothing()
            .returning(RawEvent.event_id)
        )
        return {str(event_id) for event_id in db.scalars(sqlite_statement)}
    else:
        raise RuntimeError(f"unsupported durable-inbox database dialect: {dialect}")


def accept_event_batch(
    db: Session,
    context: IngestContext,
    raw_events: list[dict[str, Any]],
) -> EventBatchResponse:
    """Durably accept raw events without running projection work in the request."""

    results: list[BatchItemResult | None] = [None] * len(raw_events)
    unique_events: list[CanonicalEvent] = []
    first_index_by_id: dict[str, int] = {}
    repeated_indices: dict[str, list[int]] = {}
    for index, raw in enumerate(raw_events):
        event_id = str(raw.get("event_id") or "unknown")
        try:
            event = CanonicalEvent.model_validate(raw)
        except ValidationError as error:
            results[index] = BatchItemResult(
                event_id=event_id,
                status="rejected_permanent",
                detail=str(error),
            )
            continue
        if event.event_id in first_index_by_id:
            repeated_indices.setdefault(event.event_id, []).append(index)
            continue
        first_index_by_id[event.event_id] = index
        unique_events.append(event)

    inserted_ids = _insert_raw_event_batch(db, context, unique_events)
    candidate_ids = [event.event_id for event in unique_events]
    persisted_ids = (
        {
            str(event_id)
            for event_id in db.scalars(
                select(RawEvent.event_id).where(
                    RawEvent.project_id == context.project_id,
                    RawEvent.event_id.in_(candidate_ids),
                )
            )
        }
        if candidate_ids
        else set()
    )

    accepted_events_by_session: dict[str, list[CanonicalEvent]] = {}
    rejected_events_by_session: dict[str, list[CanonicalEvent]] = {}
    for event in unique_events:
        index = first_index_by_id[event.event_id]
        if event.event_id in inserted_ids:
            results[index] = BatchItemResult(event_id=event.event_id, status="accepted")
            accepted_events_by_session.setdefault(event.external_session_id, []).append(event)
        elif event.event_id in persisted_ids:
            results[index] = BatchItemResult(event_id=event.event_id, status="duplicate")
        else:
            results[index] = BatchItemResult(
                event_id=event.event_id,
                status="rejected_permanent",
                detail="sequence is already occupied by another event",
            )
            rejected_events_by_session.setdefault(event.external_session_id, []).append(event)

    for event_id, indices in repeated_indices.items():
        primary = results[first_index_by_id[event_id]]
        assert primary is not None
        for index in indices:
            results[index] = (
                BatchItemResult(event_id=event_id, status="duplicate")
                if primary.status in {"accepted", "duplicate"}
                else BatchItemResult(
                    event_id=event_id,
                    status="rejected_permanent",
                    detail=primary.detail,
                )
            )

    received_at = datetime.now(UTC)
    for events in accepted_events_by_session.values():
        capture = _capture_for_event(db, context, events[0])
        capture.generation += len(events)
        capture.raw_event_count += len(events)
        capture.last_received_at = received_at
        sequences = [event.sequence for event in events if event.sequence is not None]
        if sequences:
            capture.highest_seen_sequence = max(
                capture.highest_seen_sequence or max(sequences),
                max(sequences),
            )
        terminal_events = [
            event
            for event in events
            if event.event_type in {"session.ended", "session.error"}
        ]
        if terminal_events:
            event = max(terminal_events, key=lambda item: item.sequence or -1)
            declared_last = event.attributes.get("expected_last_sequence")
            capture.expected_last_sequence = (
                int(declared_last)
                if isinstance(declared_last, int) and declared_last >= 0
                else event.sequence
            )
            capture.state = "draining"

    for events in rejected_events_by_session.values():
        capture = _capture_for_event(db, context, events[0])
        capture.permanent_rejection_count += len(events)
        capture.last_received_at = received_at

    completed_results = [result for result in results if result is not None]
    assert len(completed_results) == len(raw_events)
    accepted = sum(result.status == "accepted" for result in completed_results)
    duplicate = sum(result.status == "duplicate" for result in completed_results)
    rejected = sum(result.status == "rejected_permanent" for result in completed_results)

    return EventBatchResponse(
        accepted=accepted,
        duplicate=duplicate,
        rejected=rejected,
        items=completed_results,
    )


def missing_sequence_ranges(
    sequences: list[int], expected_last_sequence: int | None
) -> tuple[int | None, list[list[int]]]:
    if not sequences:
        return None, [] if expected_last_sequence is None else [[1, expected_last_sequence]]
    present = set(sequences)
    first = 0 if 0 in present else 1
    contiguous = first - 1
    while contiguous + 1 in present:
        contiguous += 1
    if expected_last_sequence is None:
        return contiguous, []
    missing: list[list[int]] = []
    start: int | None = None
    for sequence in range(first, expected_last_sequence + 1):
        if sequence not in present and start is None:
            start = sequence
        elif sequence in present and start is not None:
            missing.append([start, sequence - 1])
            start = None
    if start is not None:
        missing.append([start, expected_last_sequence])
    return contiguous, missing


def _project_capture(db: Session, capture: SessionCapture) -> None:
    target_generation = capture.generation
    raw_events = list(
        db.scalars(
            select(RawEvent)
            .where(
                RawEvent.project_id == capture.project_id,
                RawEvent.environment_id == capture.environment_id,
                RawEvent.external_session_id == capture.external_session_id,
                RawEvent.projected_at.is_(None),
            )
            .order_by(RawEvent.sequence.asc().nulls_last(), RawEvent.received_at, RawEvent.id)
        )
    )
    context = IngestContext(
        resolved_project_id=capture.project_id,
        resolved_environment_id=capture.environment_id,
    )
    projected_at = datetime.now(UTC)
    session_cache: dict[str, VoiceSession] = {}
    for raw_event in raw_events:
        raw_event.projection_attempts += 1
        event = CanonicalEvent.model_validate(raw_event.payload)
        persist_event(
            db,
            context,
            event,
            session_cache,
            enqueue_terminal_analysis=False,
        )
        raw_event.projected_at = projected_at
        raw_event.projection_error = None

    sequences = list(
        db.scalars(
            select(RawEvent.sequence)
            .where(
                RawEvent.project_id == capture.project_id,
                RawEvent.environment_id == capture.environment_id,
                RawEvent.external_session_id == capture.external_session_id,
                RawEvent.sequence.is_not(None),
            )
            .order_by(RawEvent.sequence)
        )
    )
    highest_contiguous, missing = missing_sequence_ranges(
        [int(item) for item in sequences if item is not None],
        capture.expected_last_sequence,
    )
    capture.highest_contiguous_sequence = highest_contiguous
    capture.missing_ranges = missing
    capture.projected_event_count = int(
        db.scalar(
            select(func.count())
            .select_from(RawEvent)
            .where(
                RawEvent.project_id == capture.project_id,
                RawEvent.environment_id == capture.environment_id,
                RawEvent.external_session_id == capture.external_session_id,
                RawEvent.projected_at.is_not(None),
            )
        )
        or 0
    )
    terminal_present = capture.expected_last_sequence is not None
    if terminal_present and not missing:
        capture.state = "complete"
        capture.completed_at = projected_at
    elif terminal_present:
        capture.state = "incomplete"
        capture.completed_at = None
    else:
        capture.state = "receiving"
        capture.completed_at = None
    capture.projected_generation = target_generation
    capture.locked_at = None
    capture.locked_by = None

    session = db.scalar(
        select(VoiceSession).where(
            VoiceSession.project_id == capture.project_id,
            VoiceSession.environment_id == capture.environment_id,
            VoiceSession.external_session_id == capture.external_session_id,
        )
    )
    if session is not None:
        capture.session_id = session.id
        session.metadata_ = {
            **(session.metadata_ or {}),
            "capture_state": capture.state,
            "capture_highest_seen_sequence": capture.highest_seen_sequence,
            "capture_highest_contiguous_sequence": capture.highest_contiguous_sequence,
            "capture_expected_last_sequence": capture.expected_last_sequence,
            "capture_missing_ranges": capture.missing_ranges,
            "capture_raw_event_count": capture.raw_event_count,
            "capture_projected_event_count": capture.projected_event_count,
        }
        if capture.state == "complete" and session.ended_at is not None:
            enqueue_completion_analysis(db, capture.project_id, session.id)
        write_session_log(
            str(session.id),
            "capture_projected",
            {
                "state": capture.state,
                "raw_event_count": capture.raw_event_count,
                "projected_event_count": capture.projected_event_count,
                "expected_last_sequence": capture.expected_last_sequence,
                "highest_contiguous_sequence": capture.highest_contiguous_sequence,
                "missing_ranges": capture.missing_ranges,
            },
            external_session_id=capture.external_session_id,
        )


def project_pending_captures(
    db: Session, *, worker_id: str, limit: int = 10
) -> int:
    """Project pending sessions in order; one transaction owns each capture row."""

    captures = list(
        db.scalars(
            select(SessionCapture)
            .where(SessionCapture.projected_generation < SessionCapture.generation)
            .order_by(SessionCapture.last_received_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    for capture in captures:
        capture.locked_at = datetime.now(UTC)
        capture.locked_by = worker_id
        _project_capture(db, capture)
    return len(captures)
