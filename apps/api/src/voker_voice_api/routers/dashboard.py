from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from voker_voice_api.database import get_db
from voker_voice_api.models import (
    Error,
    Event,
    Finding,
    FindingEvidence,
    Project,
    Span,
    UsageRecord,
)
from voker_voice_api.models import (
    Session as VoiceSession,
)

router = APIRouter(prefix="/api", tags=["dashboard"])


def timestamp(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


def json_number(value: int | float | Decimal | None) -> float | int | None:
    return float(value) if isinstance(value, Decimal) else value


def project_for_slug(db: Session, project_slug: str) -> Project:
    project = db.scalar(select(Project).where(Project.slug == project_slug))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


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


@router.get("/projects/{project_slug}/sessions")
def list_sessions(
    project_slug: str, limit: int = 30, db: Session = Depends(get_db)
) -> dict[str, list[dict[str, Any]]]:
    project = project_for_slug(db, project_slug)
    limit = max(1, min(limit, 100))
    sessions = db.scalars(
        select(VoiceSession)
        .where(VoiceSession.project_id == project.id)
        .order_by(VoiceSession.started_at.desc())
        .limit(limit)
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
    return {"items": items}


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
                    {"entity_type": evidence.entity_type, "entity_id": str(evidence.entity_id)}
                    for evidence in db.scalars(
                        select(FindingEvidence).where(FindingEvidence.finding_id == finding.id)
                    )
                ],
            }
            for finding in findings
        ],
    }
