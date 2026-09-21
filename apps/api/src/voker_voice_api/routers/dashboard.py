from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from voker_voice_api.analytics import CohortValue, latency_distribution, voice_impact_cohorts
from voker_voice_api.bootstrap import create_ingest_key
from voker_voice_api.config import REPOSITORY_ROOT, get_settings
from voker_voice_api.database import get_db
from voker_voice_api.models import (
    AnalysisRun,
    APIKey,
    CostRecord,
    Environment,
    Error,
    Event,
    Finding,
    FindingEvidence,
    Integration,
    Job,
    Project,
    Recording,
    Span,
    Turn,
    UsageRecord,
)
from voker_voice_api.models import (
    Session as VoiceSession,
)
from voker_voice_api.recordings import cloudinary_playback_url
from voker_voice_api.routers.account import require_dashboard_user
from voker_voice_api.security import generate_webhook_token

router = APIRouter(
    prefix="/api", tags=["dashboard"], dependencies=[Depends(require_dashboard_user)]
)


def timestamp(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


def json_number(value: int | float | Decimal | None) -> float | int | None:
    return float(value) if isinstance(value, Decimal) else value


def project_for_slug(db: Session, project_slug: str) -> Project:
    project = db.scalar(select(Project).where(Project.slug == project_slug))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/projects/{project_slug}/api-keys")
def list_api_keys(project_slug: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    project = project_for_slug(db, project_slug)
    keys = db.scalars(
        select(APIKey, Environment)
        .join(Environment, APIKey.environment_id == Environment.id)
        .where(APIKey.project_id == project.id)
        .order_by(APIKey.created_at.desc())
    ).all()
    return {"items": [{
        "id": str(key.id), "label": key.label, "prefix": key.prefix,
        "environment": environment.slug, "created_at": timestamp(key.created_at),
        "last_used_at": timestamp(key.last_used_at), "revoked_at": timestamp(key.revoked_at),
    } for key, environment in keys]}


@router.post("/projects/{project_slug}/api-keys", status_code=201)
def create_api_key(
    project_slug: str, payload: dict[str, str] = Body(...), db: Session = Depends(get_db)
) -> dict[str, str]:
    project = project_for_slug(db, project_slug)
    environment = db.scalar(select(Environment).where(
        Environment.project_id == project.id,
        Environment.slug == payload.get("environment", "development"),
    ))
    label = payload.get("label", "")
    if environment is None or not label:
        raise HTTPException(
            status_code=422, detail="A valid environment and key label are required"
        )
    generated = create_ingest_key(db, project=project, environment=environment, label=label)
    db.commit()
    return {"prefix": generated.prefix, "api_key": generated.raw}


@router.post("/projects/{project_slug}/api-keys/{key_id}/revoke")
def revoke_api_key(project_slug: str, key_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    project = project_for_slug(db, project_slug)
    key = db.scalar(select(APIKey).where(APIKey.id == key_id, APIKey.project_id == project.id))
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found")
    key.revoked_at = datetime.now(UTC)
    db.commit()
    return {"id": str(key.id), "status": "revoked"}


@router.get("/projects/{project_slug}/integrations")
def list_integrations(project_slug: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    project = project_for_slug(db, project_slug)
    integrations = db.scalars(
        select(Integration)
        .where(Integration.project_id == project.id)
        .order_by(Integration.created_at.desc(), Integration.id.desc())
    ).all()
    return {
        "items": [
            {
                "id": str(item.id),
                "provider": item.provider,
                "external_id": item.external_id,
                "name": item.name,
                "status": item.status,
            }
            for item in integrations
        ]
    }


@router.post("/projects/{project_slug}/integrations", status_code=201)
def create_integration(
    project_slug: str,
    payload: dict[str, str] = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Create an integration and return its delivery token exactly once."""

    project = project_for_slug(db, project_slug)
    provider = payload.get("provider", "")
    name = payload.get("name", "")
    external_id = payload.get("external_id")
    if provider not in {"vapi", "retell"} or not name:
        raise HTTPException(status_code=422, detail="provider (vapi/retell) and name are required")
    token = generate_webhook_token()
    integration = Integration(
        project_id=project.id,
        provider=provider,
        external_id=external_id or None,
        name=name,
        status="active",
        config={"webhook_token_hash": token.secret_hash},
    )
    db.add(integration)
    db.commit()
    return {"id": str(integration.id), "webhook_token": token.raw}


def session_summary(session: VoiceSession, error_count: int, event_count: int) -> dict[str, Any]:
    return {
        "id": str(session.id),
        "external_session_id": session.external_session_id,
        "trace_id": session.trace_id,
        "source": session.source,
        "status": session.status,
        "outcome": session.outcome,
        "started_at": timestamp(session.started_at),
        "ended_at": timestamp(session.ended_at),
        "error_count": error_count,
        "event_count": event_count,
    }


@router.get("/projects/{project_slug}/overview")
def project_overview(project_slug: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    project = project_for_slug(db, project_slug)
    total_sessions = (
        db.scalar(
            select(func.count())
            .select_from(VoiceSession)
            .where(VoiceSession.project_id == project.id)
        )
        or 0
    )
    active_sessions = (
        db.scalar(
            select(func.count())
            .select_from(VoiceSession)
            .where(VoiceSession.project_id == project.id, VoiceSession.status == "in_progress")
        )
        or 0
    )
    errors = (
        db.scalar(
            select(func.count())
            .select_from(Error)
            .join(VoiceSession, Error.session_id == VoiceSession.id)
            .where(VoiceSession.project_id == project.id)
        )
        or 0
    )
    durations = db.scalars(
        select(Span.duration_ms)
        .join(VoiceSession, Span.session_id == VoiceSession.id)
        .where(VoiceSession.project_id == project.id, Span.duration_ms.is_not(None))
    ).all()
    avg_duration = (sum(float(item) for item in durations) / len(durations)) if durations else None
    return {
        "project": {"id": str(project.id), "name": project.name, "slug": project.slug},
        "metrics": {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "error_count": errors,
            "average_span_duration_ms": avg_duration,
        },
    }


@router.get("/projects/{project_slug}/analytics/overview")
def analytics_overview(project_slug: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Bounded project aggregates that retain unknown costs/metrics as unknown."""

    project = project_for_slug(db, project_slug)
    sessions = list(
        db.scalars(
            select(VoiceSession).where(VoiceSession.project_id == project.id)
        )
    )
    completed = [item for item in sessions if item.status == "completed"]
    outcome_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for item in sessions:
        source_counts[item.source] = source_counts.get(item.source, 0) + 1
        if item.outcome:
            outcome_counts[item.outcome] = outcome_counts.get(item.outcome, 0) + 1
    costs = list(
        db.scalars(
            select(CostRecord)
            .join(VoiceSession, CostRecord.session_id == VoiceSession.id)
            .where(VoiceSession.project_id == project.id)
        )
    )
    events_by_session: dict[object, list[Event]] = {item.id: [] for item in sessions}
    if sessions:
        events = db.scalars(select(Event).where(Event.session_id.in_(events_by_session))).all()
        for event in events:
            events_by_session[event.session_id].append(event)
    cohort_values = []
    for item in sessions:
        events = events_by_session[item.id]
        stt_durations = [
            float(event.duration_ms)
            for event in events
            if event.event_type == "stt.completed" and event.duration_ms is not None
        ]
        cohort_values.append(
            CohortValue(
                key=str(item.id),
                outcome=item.outcome,
                interruption_count=sum(
                    event.event_type == "voice.interruption" for event in events
                ),
                stt_duration_ms=max(stt_durations) if stt_durations else None,
            )
        )
    spans_by_kind: dict[str, list[float]] = {"stt": [], "llm": [], "tool": [], "tts": []}
    if sessions:
        spans = db.scalars(
            select(Span).where(
                Span.session_id.in_(events_by_session), Span.duration_ms.is_not(None)
            )
        ).all()
        for span in spans:
            if span.kind in spans_by_kind:
                spans_by_kind[span.kind].append(float(span.duration_ms))
    return {
        "session_count": len(sessions),
        "completed_session_count": len(completed),
        "outcomes": outcome_counts,
        "sources": source_counts,
        "cost": {
            "amount_micros": sum(item.amount_micros for item in costs) if costs else None,
            "currency": "USD" if costs else None,
            "record_count": len(costs),
            "estimated_record_count": sum(1 for item in costs if item.is_estimate),
        },
        "voice_impact_cohorts": voice_impact_cohorts(cohort_values),
        "latency": {kind: latency_distribution(values) for kind, values in spans_by_kind.items()},
    }


@router.get("/projects/{project_slug}/sessions")
def list_sessions(
    project_slug: str,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = None,
    source: str | None = None,
    search: str | None = Query(default=None, max_length=255),
    sort: str = Query(
        default="started_at_desc",
        pattern="^(started_at_desc|started_at_asc|errors_desc|events_desc)$",
    ),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = project_for_slug(db, project_slug)
    conditions = [VoiceSession.project_id == project.id]
    if status:
        conditions.append(VoiceSession.status == status)
    if source:
        conditions.append(VoiceSession.source == source)
    if search:
        conditions.append(VoiceSession.external_session_id.ilike(f"%{search}%"))
    total = db.scalar(select(func.count()).select_from(VoiceSession).where(*conditions)) or 0
    ordering = {
        "started_at_desc": (VoiceSession.started_at.desc(), VoiceSession.id.desc()),
        "started_at_asc": (VoiceSession.started_at.asc(), VoiceSession.id.asc()),
    }
    # Error/event ordering uses correlated counts so sorting remains server-side
    # and therefore stable across pagination.
    if sort == "errors_desc":
        error_total = (
            select(func.count())
            .select_from(Error)
            .where(Error.session_id == VoiceSession.id)
            .correlate(VoiceSession)
            .scalar_subquery()
        )
        order_by = (error_total.desc(), VoiceSession.started_at.desc(), VoiceSession.id.desc())
    elif sort == "events_desc":
        event_total = (
            select(func.count())
            .select_from(Event)
            .where(Event.session_id == VoiceSession.id)
            .correlate(VoiceSession)
            .scalar_subquery()
        )
        order_by = (event_total.desc(), VoiceSession.started_at.desc(), VoiceSession.id.desc())
    else:
        order_by = ordering[sort]
    sessions = db.scalars(
        select(VoiceSession).where(*conditions).order_by(*order_by).offset(offset).limit(limit)
    ).all()
    items = []
    for session in sessions:
        error_count = (
            db.scalar(select(func.count()).select_from(Error).where(Error.session_id == session.id))
            or 0
        )
        event_count = (
            db.scalar(select(func.count()).select_from(Event).where(Event.session_id == session.id))
            or 0
        )
        items.append(session_summary(session, error_count, event_count))
    return {"items": items, "page": {"offset": offset, "limit": limit, "total": total}}


@router.get("/projects/{project_slug}/sessions/{session_id}")
def get_session_trace(
    project_slug: str, session_id: str, db: Session = Depends(get_db)
) -> dict[str, Any]:
    project = project_for_slug(db, project_slug)
    session = db.scalar(
        select(VoiceSession).where(
            VoiceSession.project_id == project.id, VoiceSession.id == session_id
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    events = db.scalars(
        select(Event)
        .where(Event.session_id == session.id)
        .order_by(Event.occurred_at, Event.sequence, Event.id)
    ).all()
    spans = db.scalars(
        select(Span).where(Span.session_id == session.id).order_by(Span.started_at, Span.id)
    ).all()
    errors = db.scalars(
        select(Error).where(Error.session_id == session.id).order_by(Error.created_at, Error.id)
    ).all()
    usage = db.scalars(select(UsageRecord).where(UsageRecord.session_id == session.id)).all()
    findings = db.scalars(
        select(Finding).where(Finding.session_id == session.id).order_by(Finding.created_at.desc())
    ).all()
    analysis_runs = db.scalars(
        select(AnalysisRun)
        .where(AnalysisRun.session_id == session.id)
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
    ).all()
    recordings = db.scalars(
        select(Recording).where(Recording.session_id == session.id).order_by(Recording.created_at)
    ).all()
    turns = db.scalars(
        select(Turn).where(Turn.session_id == session.id).order_by(Turn.sequence, Turn.id)
    ).all()
    event_by_id = {event.id: event for event in events}
    span_by_id = {span.id: span for span in spans}
    turn_ids = {turn.id for turn in turns}

    def evidence_target(evidence: FindingEvidence) -> dict[str, str | None]:
        """Resolve opaque evidence rows to directly addressable trace targets."""
        event_id = None
        turn_id = None
        if evidence.entity_type == "event":
            event = event_by_id.get(evidence.entity_id)
            event_id = str(event.id) if event else None
            turn_id = str(event.turn_id) if event and event.turn_id else None
        elif evidence.entity_type == "span":
            span = span_by_id.get(evidence.entity_id)
            turn_id = str(span.turn_id) if span and span.turn_id else None
            related_event = next(
                (event for event in events if event.span_id == evidence.entity_id), None
            )
            event_id = str(related_event.id) if related_event else None
        elif evidence.entity_type == "turn" and evidence.entity_id in turn_ids:
            turn_id = str(evidence.entity_id)
        return {
            "entity_type": evidence.entity_type,
            "entity_id": str(evidence.entity_id),
            "event_id": event_id,
            "turn_id": turn_id,
        }
    return {
        "session": session_summary(session, len(errors), len(events)),
        "events": [
            {
                "id": str(event.id),
                "event_id": event.event_id,
                "event_type": event.event_type,
                "status": event.status,
                "occurred_at": timestamp(event.occurred_at),
                "duration_ms": json_number(event.duration_ms),
                "payload": event.payload,
            }
            for event in events
        ],
        "turns": [
            {
                "id": str(turn.id),
                "external_turn_id": turn.external_turn_id,
                "sequence": turn.sequence,
                "speaker": turn.speaker,
                "started_at": timestamp(turn.started_at),
                "ended_at": timestamp(turn.ended_at),
                "transcript": turn.transcript,
                "attributes": turn.attributes,
            }
            for turn in turns
        ],
        "spans": [
            {
                "id": str(span.id),
                "external_span_id": span.external_span_id,
                "parent_external_span_id": span.parent_external_span_id,
                "name": span.name,
                "kind": span.kind,
                "status": span.status,
                "source": span.source,
                "started_at": timestamp(span.started_at),
                "ended_at": timestamp(span.ended_at),
                "duration_ms": json_number(span.duration_ms),
                "attributes": span.attributes,
            }
            for span in spans
        ],
        "errors": [
            {
                "id": str(error.id),
                "type": error.type,
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
                "retry_count": error.retry_count,
                "event_id": str(error.event_id) if error.event_id else None,
                "created_at": timestamp(error.created_at),
            }
            for error in errors
        ],
        "usage": [
            {
                "provider": item.provider,
                "model": item.model,
                "input_tokens": item.input_tokens,
                "output_tokens": item.output_tokens,
                "total_tokens": item.total_tokens,
                "audio_seconds": json_number(item.audio_seconds),
                "tts_characters": item.tts_characters,
            }
            for item in usage
        ],
        "findings": [
            {
                **{
                    "id": str(finding.id),
                    "type": finding.type,
                    "certainty": finding.certainty,
                    "severity": finding.severity,
                    "statement": finding.statement,
                    "confidence": json_number(finding.confidence),
                    "rule_id": finding.rule_id,
                    "created_at": timestamp(finding.created_at),
                },
                "evidence": [
                    evidence_target(evidence)
                    for evidence in db.scalars(
                        select(FindingEvidence).where(FindingEvidence.finding_id == finding.id)
                    )
                ],
            }
            for finding in findings
        ],
        "analysis_runs": [
            {
                "id": str(run.id),
                "status": run.status,
                "analysis_version": run.analysis_version,
                "prompt_version": run.prompt_version,
                "model": run.model,
                "result": run.result,
                "error": run.error,
                "created_at": timestamp(run.created_at),
            }
            for run in analysis_runs
        ],
        "recordings": [
            {
                "id": str(recording.id),
                "source": recording.source,
                "external_id": recording.external_id,
                "duration_ms": recording.duration_ms,
                "media_type": recording.media_type,
                "status": recording.status,
                "expires_at": timestamp(recording.expires_at),
            }
            for recording in recordings
        ],
    }


@router.post("/projects/{project_slug}/sessions/{session_id}/analysis")
def request_reanalysis(
    project_slug: str, session_id: str, db: Session = Depends(get_db)
) -> dict[str, str]:
    """Queue a new deterministic and semantic pass without mutating prior analysis runs."""

    project = project_for_slug(db, project_slug)
    session = db.scalar(
        select(VoiceSession).where(
            VoiceSession.project_id == project.id, VoiceSession.id == session_id
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    for job_type in ("run_deterministic_analysis", "run_semantic_analysis"):
        db.add(Job(project_id=project.id, type=job_type, payload={"session_id": str(session.id)}))
    db.commit()
    return {"status": "queued"}


@router.post("/projects/{project_slug}/sessions/{session_id}/recordings", status_code=201)
def attach_recording_metadata(
    project_slug: str,
    session_id: str,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Attach optional external/private recording metadata without copying audio."""

    project = project_for_slug(db, project_slug)
    session = db.scalar(
        select(VoiceSession).where(
            VoiceSession.project_id == project.id, VoiceSession.id == session_id
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    source = payload.get("source")
    if not isinstance(source, str) or not source:
        raise HTTPException(status_code=422, detail="recording source is required")
    duration_ms = payload.get("duration_ms")
    if duration_ms is not None and (not isinstance(duration_ms, int) or duration_ms < 0):
        raise HTTPException(status_code=422, detail="duration_ms must be a non-negative integer")
    external_id = payload.get("external_id")
    asset_reference = payload.get("asset_reference")
    media_type = payload.get("media_type")
    recording_status = payload.get("status")
    recording = Recording(
        session_id=session.id,
        source=source,
        external_id=external_id if isinstance(external_id, str) else None,
        asset_reference=asset_reference if isinstance(asset_reference, str) else None,
        duration_ms=duration_ms,
        media_type=media_type if isinstance(media_type, str) else None,
        status=recording_status if isinstance(recording_status, str) else "available",
    )
    db.add(recording)
    db.commit()
    return {"id": str(recording.id), "status": recording.status}


@router.delete("/projects/{project_slug}/sessions/{session_id}/recordings/{recording_id}")
def delete_recording_metadata(
    project_slug: str,
    session_id: str,
    recording_id: str,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Revoke optional recording access without deleting canonical trace data."""

    project = project_for_slug(db, project_slug)
    recording = db.scalar(
        select(Recording)
        .join(VoiceSession, Recording.session_id == VoiceSession.id)
        .where(
            VoiceSession.project_id == project.id,
            VoiceSession.id == session_id,
            Recording.id == recording_id,
        )
    )
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    recording.asset_reference = None
    recording.status = "deleted"
    db.commit()
    return {"id": str(recording.id), "status": recording.status}


@router.get(
    "/projects/{project_slug}/sessions/{session_id}/recordings/{recording_id}/playback",
    response_model=None,
)
def redirect_to_recording_playback(
    project_slug: str,
    session_id: str,
    recording_id: str,
    db: Session = Depends(get_db),
) -> RedirectResponse | FileResponse:
    """Issue playback through a short-lived signed URL; audio never transits this API."""

    project = project_for_slug(db, project_slug)
    recording = db.scalar(
        select(Recording)
        .join(VoiceSession, Recording.session_id == VoiceSession.id)
        .where(
            VoiceSession.project_id == project.id,
            VoiceSession.id == session_id,
            Recording.id == recording_id,
        )
    )
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    if recording.status != "available":
        raise HTTPException(status_code=410, detail="Recording is no longer available")
    # Development seed recordings intentionally use a repository fixture. This
    # path is unavailable outside development and is constrained to the repo.
    if recording.source == "local":
        if get_settings().app_env != "development" or not recording.asset_reference:
            raise HTTPException(status_code=404, detail="Local demo recording is unavailable")
        path = (REPOSITORY_ROOT / recording.asset_reference).resolve()
        if REPOSITORY_ROOT not in path.parents or not path.is_file():
            raise HTTPException(status_code=404, detail="Local demo recording was not found")
        return FileResponse(path, media_type=recording.media_type or "audio/mpeg")
    try:
        url = cloudinary_playback_url(recording, get_settings())
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return RedirectResponse(url=url, status_code=307)
