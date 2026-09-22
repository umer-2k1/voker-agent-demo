import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from voker_voice_api.analysis_versions import ANALYSIS_SCHEMA_VERSION, prompt_version_for_job
from voker_voice_api.config import get_settings
from voker_voice_api.costs import estimate_llm_cost_micros
from voker_voice_api.models import (
    Agent,
    AgentRun,
    AgentVersion,
    AnalysisRun,
    APIKey,
    CostRecord,
    Error,
    Event,
    Job,
    Recording,
    Span,
    Turn,
    UsageRecord,
)
from voker_voice_api.models import (
    Session as VoiceSession,
)
from voker_voice_api.recordings import recording_expiry, validate_recording_metadata
from voker_voice_api.schemas import BatchItemResult, CanonicalEvent, EventBatchResponse

TERMINAL_STATUSES = {"ok", "error", "cancelled", "timeout"}
TERMINAL_SUFFIXES = (
    ".completed",
    ".ended",
    ".error",
    ".cancelled",
    ".timeout",
    ".interrupted",
)


def comparable_datetime(value: datetime) -> datetime:
    """Normalize database-returned naive UTC timestamps for safe producer-time comparison."""

    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def is_earlier(candidate: datetime, current: datetime) -> bool:
    return comparable_datetime(candidate) < comparable_datetime(current)


def is_later(candidate: datetime, current: datetime) -> bool:
    return comparable_datetime(candidate) > comparable_datetime(current)


@dataclass(frozen=True)
class IngestContext:
    api_key: APIKey | None = None
    resolved_project_id: uuid.UUID | None = None
    resolved_environment_id: uuid.UUID | None = None

    @property
    def project_id(self) -> uuid.UUID:
        if self.api_key is not None:
            return self.api_key.project_id
        if self.resolved_project_id is not None:
            return self.resolved_project_id
        raise ValueError("Ingest context has no project")

    @property
    def environment_id(self) -> uuid.UUID:
        if self.api_key is not None:
            return self.api_key.environment_id
        if self.resolved_environment_id is not None:
            return self.resolved_environment_id
        raise ValueError("Ingest context has no environment")


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


def resolve_agent_version(
    db: Session, agent: Agent | None, event: CanonicalEvent
) -> AgentVersion | None:
    if agent is None or event.agent is None or not event.agent.version:
        return None
    version = db.scalar(
        select(AgentVersion).where(
            AgentVersion.agent_id == agent.id,
            AgentVersion.version == event.agent.version,
        )
    )
    if version is None:
        version = AgentVersion(agent_id=agent.id, version=event.agent.version, metadata_={})
        db.add(version)
        db.flush()
    return version


def is_terminal_event(event: CanonicalEvent) -> bool:
    return event.event_type.endswith(TERMINAL_SUFFIXES)


def merge_terminal_status(current: str, event: CanonicalEvent) -> str:
    """Never let an earlier lifecycle event reopen a terminal operation."""

    if current in TERMINAL_STATUSES and not is_terminal_event(event):
        return current
    return event.status.value


def session_status_for_event(event: CanonicalEvent) -> str:
    if event.status.value == "error":
        return "failed"
    if event.status.value == "cancelled":
        return "cancelled"
    if event.status.value == "timeout":
        return "incomplete"
    return "completed"


def enqueue_completion_analysis(db: Session, project_id: uuid.UUID, session_id: uuid.UUID) -> None:
    """Queue each completion analysis once while preserving explicit manual re-analysis."""

    session_value = str(session_id)
    existing = list(
        db.scalars(
            select(Job).where(
                Job.project_id == project_id,
                Job.type.in_(("run_deterministic_analysis", "run_semantic_analysis")),
            )
        )
    )
    existing_types = {
        job.type
        for job in existing
        if job.payload.get("session_id") == session_value
        and job.payload.get("trigger", "session_completion") == "session_completion"
    }
    for job_type in ("run_deterministic_analysis", "run_semantic_analysis"):
        if job_type not in existing_types:
            prompt_prefix = (
                "deterministic" if job_type == "run_deterministic_analysis" else "semantic"
            )
            latest_version = db.scalar(
                select(func.max(AnalysisRun.analysis_version)).where(
                    AnalysisRun.session_id == session_id,
                    AnalysisRun.prompt_version.like(f"{prompt_prefix}-%"),
                )
            )
            analysis_run = AnalysisRun(
                session_id=session_id,
                status="queued",
                analysis_version=int(latest_version or 0) + 1,
                prompt_version=prompt_version_for_job(job_type),
                schema_version=ANALYSIS_SCHEMA_VERSION,
            )
            db.add(analysis_run)
            db.flush()
            db.add(
                Job(
                    project_id=project_id,
                    type=job_type,
                    payload={
                        "session_id": session_value,
                        "analysis_run_id": str(analysis_run.id),
                        "trigger": "session_completion",
                    },
                )
            )


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
        version = resolve_agent_version(db, agent, event)
        session = VoiceSession(
            project_id=context.project_id,
            environment_id=context.environment_id,
            agent_id=agent.id if agent else None,
            agent_version_id=version.id if version else None,
            external_session_id=event.external_session_id,
            trace_id=event.trace_id,
            source=event.source.integration or "custom",
            status="in_progress",
            started_at=event.occurred_at,
            metadata_=event.attributes if event.event_type == "session.started" else {},
        )
        db.add(session)
        db.flush()
    else:
        if is_earlier(event.occurred_at, session.started_at):
            session.started_at = event.occurred_at
        if event.event_type == "session.started":
            session.metadata_ = {**session.metadata_, **event.attributes}
        agent = resolve_agent(db, context.project_id, event)
        version = resolve_agent_version(db, agent, event)
        if agent is not None and session.agent_id is None:
            session.agent_id = agent.id
        if version is not None and session.agent_version_id is None:
            session.agent_version_id = version.id
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
            latest_sequence = db.scalar(
                select(func.coalesce(func.max(Turn.sequence), -1)).where(
                    Turn.session_id == session.id
                )
            )
            sequence = int(latest_sequence if latest_sequence is not None else -1) + 1
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
    elif is_earlier(event.occurred_at, turn.started_at):
        turn.started_at = event.occurred_at
    speaker = event.attributes.get("speaker")
    transcript = event.attributes.get("transcript")
    if not isinstance(transcript, str):
        candidate = event.input if event.event_type.startswith(("user.", "stt.")) else event.output
        transcript = candidate.get("text") if isinstance(candidate, dict) else None
    if isinstance(speaker, str) and speaker:
        turn.speaker = speaker[:32]
    elif event.event_type.startswith(("user.", "stt.")):
        turn.speaker = "user"
    elif event.event_type.startswith(("agent.", "assistant.", "tts.")):
        turn.speaker = "agent"
    if isinstance(transcript, str) and transcript:
        turn.transcript = transcript
    if event.event_type.endswith((".completed", ".ended", ".abandoned")):
        if turn.ended_at is None or is_later(event.occurred_at, turn.ended_at):
            turn.ended_at = event.occurred_at
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
        agent = resolve_agent(db, session.project_id, event)
        version = resolve_agent_version(db, agent, event)
        run_attributes = dict(event.attributes)
        if event.parent_agent_run_id:
            run_attributes["parent_agent_run_id"] = event.parent_agent_run_id
        run = AgentRun(
            session_id=session.id,
            turn_id=turn.id if turn else None,
            external_run_id=event.agent_run_id,
            name=event.agent.name if event.agent and event.agent.name else "agent-run",
            status=event.status.value,
            started_at=event.occurred_at,
            ended_at=event.occurred_at if is_terminal_event(event) else None,
            agent_id=agent.id if agent else None,
            agent_version_id=version.id if version else None,
            attributes=run_attributes,
        )
        db.add(run)
        db.flush()
    else:
        run.status = merge_terminal_status(run.status, event)
        if is_earlier(event.occurred_at, run.started_at):
            run.started_at = event.occurred_at
        run.turn_id = run.turn_id or (turn.id if turn else None)
        run.attributes = {**run.attributes, **event.attributes}
        if event.parent_agent_run_id:
            run.attributes["parent_agent_run_id"] = event.parent_agent_run_id
        if is_terminal_event(event):
            if run.ended_at is None or is_later(event.occurred_at, run.ended_at):
                run.ended_at = event.occurred_at
        agent = resolve_agent(db, session.project_id, event)
        version = resolve_agent_version(db, agent, event)
        run.agent_id = run.agent_id or (agent.id if agent else None)
        run.agent_version_id = run.agent_version_id or (version.id if version else None)
    parent_external_id = event.parent_agent_run_id
    if parent_external_id:
        parent = db.scalar(
            select(AgentRun).where(
                AgentRun.session_id == session.id,
                AgentRun.external_run_id == parent_external_id,
            )
        )
        if parent is not None:
            run.parent_run_id = parent.id
    unresolved_children = db.scalars(
        select(AgentRun).where(
            AgentRun.session_id == session.id,
            AgentRun.parent_run_id.is_(None),
        )
    )
    for child in unresolved_children:
        if child.attributes.get("parent_agent_run_id") == run.external_run_id:
            child.parent_run_id = run.id
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
    terminal = is_terminal_event(event)
    span_name = event.attributes.get("name")
    if not isinstance(span_name, str) or not span_name:
        span_name = event.event_type.rsplit(".", maxsplit=1)[0]
    if span is None:
        span = Span(
            session_id=session.id,
            turn_id=turn.id if turn else None,
            agent_run_id=run.id if run else None,
            external_span_id=event.span_id,
            parent_external_span_id=event.parent_span_id,
            name=span_name,
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
        span.status = merge_terminal_status(span.status, event)
        if is_earlier(event.occurred_at, span.started_at):
            span.started_at = event.occurred_at
        if terminal:
            if span.ended_at is None or is_later(event.occurred_at, span.ended_at):
                span.ended_at = event.occurred_at
        if event.duration_ms is not None:
            span.duration_ms = event.duration_ms
        span.attributes = {**span.attributes, **event.attributes}
        if event.input is not None:
            span.input_ = event.input
        if event.output is not None:
            span.output = event.output
        span.turn_id = span.turn_id or (turn.id if turn else None)
        span.agent_run_id = span.agent_run_id or (run.id if run else None)

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
    provider_cost = event.attributes.get("provider_cost_micros")
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
        estimate = (
            None
            if isinstance(provider_cost, (int, float))
            else estimate_llm_cost_micros(
                provider=event.usage.provider,
                model=event.usage.model,
                input_tokens=event.usage.input_tokens,
                output_tokens=event.usage.output_tokens,
                cached_tokens=event.usage.cached_tokens,
            )
        )
        if estimate is not None:
            amount_micros, rate_card = estimate
            db.add(
                CostRecord(
                    session_id=session.id,
                    span_id=span.id if span else None,
                    amount_micros=amount_micros,
                    source="estimate",
                    rate_card_version=rate_card.version,
                    is_estimate=True,
                )
            )
    if isinstance(provider_cost, (int, float)) and provider_cost >= 0:
        db.add(
            CostRecord(
                session_id=session.id,
                span_id=span.id if span else None,
                amount_micros=round(provider_cost),
                source="provider",
                rate_card_version=None,
                is_estimate=False,
            )
        )
    if event.event_type == "recording.available":
        asset_reference = event.attributes.get("recording_url")
        external_id = event.attributes.get("recording_external_id")
        source = event.source.provider or event.source.integration or "external"
        if source not in {"cloudinary", "livekit", "vapi", "retell", "external", "local"}:
            source = "external"
        existing_recording = db.scalar(
            select(Recording).where(
                Recording.session_id == session.id,
                Recording.source == source,
                Recording.external_id == (external_id if isinstance(external_id, str) else None),
            )
        )
        status_value = "available" if isinstance(asset_reference, str) else "unavailable"
        validate_recording_metadata(
            source=source,
            status=status_value,
            asset_reference=asset_reference if isinstance(asset_reference, str) else None,
        )
        if existing_recording is None:
            db.add(
                Recording(
                    session_id=session.id,
                    source=source,
                    external_id=external_id if isinstance(external_id, str) else None,
                    asset_reference=asset_reference if isinstance(asset_reference, str) else None,
                    duration_ms=(
                        round(event.duration_ms) if event.duration_ms is not None else None
                    ),
                    media_type=(
                        str(event.attributes["media_type"])
                        if event.attributes.get("media_type")
                        else None
                    ),
                    status=status_value,
                    expires_at=recording_expiry(None, get_settings()),
                )
            )
        else:
            if isinstance(asset_reference, str):
                existing_recording.asset_reference = asset_reference
                existing_recording.status = "available"
    if event.event_type in {"session.ended", "session.error"}:
        session.status = session_status_for_event(event)
        if session.ended_at is None or is_later(event.occurred_at, session.ended_at):
            session.ended_at = event.occurred_at
        outcome = event.attributes.get("outcome")
        outcome_source = event.attributes.get("outcome_source")
        if isinstance(outcome, str):
            session.outcome = outcome
        if isinstance(outcome_source, str):
            session.outcome_source = outcome_source
        if event.event_type == "session.ended":
            enqueue_completion_analysis(db, context.project_id, session.id)
    elif event.event_type == "outcome.recorded":
        outcome = event.attributes.get("outcome")
        recorded_source = event.attributes.get("source")
        if isinstance(outcome, str):
            session.outcome = outcome
            session.outcome_source = (
                recorded_source if isinstance(recorded_source, str) else "explicit"
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
