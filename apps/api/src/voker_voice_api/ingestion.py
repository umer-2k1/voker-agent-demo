import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from voker_voice_api.models import (
    Agent,
    AgentRun,
    APIKey,
    Error,
    Event,
    Job,
    Span,
    Turn,
    UsageRecord,
)
from voker_voice_api.models import (
    Session as VoiceSession,
)
from voker_voice_api.schemas import BatchItemResult, CanonicalEvent, EventBatchResponse


@dataclass(frozen=True)
class IngestContext:
    api_key: APIKey

    @property
    def project_id(self) -> uuid.UUID:
        return self.api_key.project_id

    @property
    def environment_id(self) -> uuid.UUID:
        return self.api_key.environment_id


def resolve_agent(db: Session, project_id: uuid.UUID, event: CanonicalEvent) -> Agent | None:
    if event.agent is None or event.agent.name is None:
        return None
    slug = event.agent.name.lower().replace(" ", "-")[:100]
    agent = db.scalar(select(Agent).where(Agent.project_id == project_id, Agent.slug == slug))
    if agent is None:
        agent = Agent(
            project_id=project_id,
            name=event.agent.name,
            slug=slug,
            source=event.source.integration or "custom",
            external_id=event.agent.id,
        )
        db.add(agent)
        db.flush()
    return agent


def session_for_event(db: Session, context: IngestContext, event: CanonicalEvent) -> VoiceSession:
    session = db.scalar(
        select(VoiceSession).where(
            VoiceSession.project_id == context.project_id,
            VoiceSession.environment_id == context.environment_id,
            VoiceSession.external_session_id == event.external_session_id,
        )
    )
    if session is None:
        agent = resolve_agent(db, context.project_id, event)
        session = VoiceSession(
            project_id=context.project_id,
            environment_id=context.environment_id,
            agent_id=agent.id if agent else None,
            external_session_id=event.external_session_id,
            trace_id=event.trace_id,
            source=event.source.integration or "custom",
            status="in_progress",
            started_at=event.occurred_at,
            metadata_={},
        )
        db.add(session)
        db.flush()
    return session


def upsert_turn(db: Session, session: VoiceSession, event: CanonicalEvent) -> Turn | None:
    if event.turn_id is None:
        return None
    turn = db.scalar(
        select(Turn).where(Turn.session_id == session.id, Turn.external_turn_id == event.turn_id)
    )
    if turn is None:
        sequence = event.sequence
        if sequence is None:
            sequence = (
                db.scalar(
                    select(func.coalesce(func.max(Turn.sequence), -1)).where(
                        Turn.session_id == session.id
                    )
                )
                + 1
            )
        turn = Turn(
            session_id=session.id,
            external_turn_id=event.turn_id,
            sequence=sequence,
            speaker="unknown",
            started_at=event.occurred_at,
            attributes={},
        )
        db.add(turn)
        db.flush()
    return turn


def upsert_agent_run(
    db: Session, session: VoiceSession, turn: Turn | None, event: CanonicalEvent
) -> AgentRun | None:
    if event.agent_run_id is None:
        return None
    run = db.scalar(
        select(AgentRun).where(
            AgentRun.session_id == session.id,
            AgentRun.external_run_id == event.agent_run_id,
        )
    )
    if run is None:
        run = AgentRun(
            session_id=session.id,
            turn_id=turn.id if turn else None,
            external_run_id=event.agent_run_id,
            name=event.agent.name if event.agent and event.agent.name else "agent-run",
            status=event.status.value,
            started_at=event.occurred_at,
            attributes={},
        )
        db.add(run)
        db.flush()
    return run


def upsert_span(
    db: Session,
    session: VoiceSession,
    turn: Turn | None,
    run: AgentRun | None,
    event: CanonicalEvent,
) -> Span | None:
    if event.span_id is None:
        return None
    span = db.scalar(
        select(Span).where(
            Span.session_id == session.id,
            Span.external_span_id == event.span_id,
        )
    )
    terminal = event.event_type.endswith((".completed", ".error", ".cancelled", ".timeout"))
    if span is None:
        span = Span(
            session_id=session.id,
            turn_id=turn.id if turn else None,
            agent_run_id=run.id if run else None,
            external_span_id=event.span_id,
            parent_external_span_id=event.parent_span_id,
            name=event.event_type,
            kind=event.event_type.split(".", maxsplit=1)[0],
            status=event.status.value,
            source=event.source.provider or event.source.integration,
            started_at=event.occurred_at,
            ended_at=event.occurred_at if terminal else None,
            duration_ms=event.duration_ms,
            attributes=event.attributes,
            input_=event.input,
            output=event.output,
        )
        db.add(span)
        db.flush()
    else:
        span.status = event.status.value
        span.ended_at = event.occurred_at if terminal else span.ended_at
        span.duration_ms = event.duration_ms or span.duration_ms
        span.attributes = {**span.attributes, **event.attributes}
        span.input_ = event.input or span.input_
        span.output = event.output or span.output

    if event.parent_span_id:
        parent = db.scalar(
            select(Span).where(
                Span.session_id == session.id,
                Span.external_span_id == event.parent_span_id,
            )
        )
        if parent:
            span.parent_span_id = parent.id
        else:
            span.parent_external_span_id = event.parent_span_id

    db.execute(
        update(Span)
        .where(
            Span.session_id == session.id,
            Span.parent_external_span_id == span.external_span_id,
            Span.parent_span_id.is_(None),
        )
        .values(parent_span_id=span.id)
    )
    return span


def persist_event(db: Session, context: IngestContext, event: CanonicalEvent) -> str:
    duplicate = db.scalar(
        select(Event.id).where(
            Event.project_id == context.project_id, Event.event_id == event.event_id
        )
    )
    if duplicate:
        return "duplicate"

    session = session_for_event(db, context, event)
    turn = upsert_turn(db, session, event)
    run = upsert_agent_run(db, session, turn, event)
    span = upsert_span(db, session, turn, run, event)
    payload = event.model_dump(mode="json")
    persisted_event = Event(
        project_id=context.project_id,
        session_id=session.id,
        span_id=span.id if span else None,
        turn_id=turn.id if turn else None,
        agent_run_id=run.id if run else None,
        event_id=event.event_id,
        event_type=event.event_type,
        sequence=event.sequence,
        occurred_at=event.occurred_at,
        status=event.status.value,
        duration_ms=event.duration_ms,
        payload=payload,
        raw_payload=payload,
    )
    db.add(persisted_event)
    db.flush()

    if event.error:
        db.add(
            Error(
                session_id=session.id,
                span_id=span.id if span else None,
                event_id=persisted_event.id,
                type=event.error.type,
                code=event.error.code,
                message=event.error.message,
                retryable=event.error.retryable,
                retry_count=event.error.retry_count,
                provider_request_id=event.error.provider_request_id,
                stacktrace=event.error.stacktrace,
            )
        )
    if event.usage:
        db.add(
            UsageRecord(
                session_id=session.id,
                span_id=span.id if span else None,
                provider=event.usage.provider,
                model=event.usage.model,
                input_tokens=event.usage.input_tokens,
                output_tokens=event.usage.output_tokens,
                cached_tokens=event.usage.cached_tokens,
                total_tokens=event.usage.total_tokens,
                audio_seconds=event.usage.audio_seconds,
                tts_characters=event.usage.tts_characters,
                attributes={},
            )
        )
    if event.event_type == "session.ended":
        session.status = "completed"
        session.ended_at = event.occurred_at
        db.add(
            Job(
                project_id=context.project_id,
                type="run_deterministic_analysis",
                payload={"session_id": str(session.id)},
            )
        )
    return "accepted"


def ingest_batch(
    db: Session, context: IngestContext, raw_events: list[dict[str, Any]]
) -> EventBatchResponse:
    results: list[BatchItemResult] = []
    accepted = duplicate = rejected = 0
    for raw_event in raw_events:
        event_id = str(raw_event.get("event_id", "unknown"))
        try:
            event = CanonicalEvent.model_validate(raw_event)
            with db.begin_nested():
                status = persist_event(db, context, event)
            if status == "accepted":
                accepted += 1
            else:
                duplicate += 1
            results.append(BatchItemResult(event_id=event.event_id, status=status))
        except Exception as error:  # A bad item must not discard an entire batch.
            rejected += 1
            results.append(BatchItemResult(event_id=event_id, status="rejected", detail=str(error)))
    return EventBatchResponse(
        accepted=accepted, duplicate=duplicate, rejected=rejected, items=results
    )


def sse_payload(event: CanonicalEvent) -> str:
    return json.dumps(
        {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "occurred_at": event.occurred_at.isoformat(),
        },
        separators=(",", ":"),
    )
