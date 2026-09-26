"""Append-only, session-scoped diagnostics for local investigation.

These files intentionally mirror the canonical lifecycle rather than replace it.
They make it possible to see what the API accepted, persisted, queued, and
processed when a voice provider disconnects before delivering a final event.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from voker_voice_api.config import get_settings

_LOCK = threading.Lock()
_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|password|secret|access[_-]?token|refresh[_-]?token)",
    re.I,
)
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_value(value: Any) -> Any:
    """Preserve diagnostic evidence without ever writing credentials to disk."""

    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else _safe_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    return value


def _path_for(session_id: str) -> Path:
    filename = _SAFE_FILENAME.sub("_", session_id).strip("._") or "unknown-session"
    return get_settings().session_log_dir / f"{filename}.jsonl"


def write_session_log(
    session_id: str,
    stage: str,
    data: dict[str, Any] | None = None,
    *,
    external_session_id: str | None = None,
) -> None:
    """Write one JSONL record; diagnostics must never interrupt ingestion."""

    try:
        path = _path_for(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        record: dict[str, Any] = {
            "logged_at": datetime.now(UTC).isoformat(),
            "stage": stage,
            "session_id": session_id,
        }
        if external_session_id:
            record["external_session_id"] = external_session_id
        if data:
            record["data"] = _safe_value(data)
        with _LOCK, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str, separators=(",", ":")) + "\n")
    except Exception:
        # Observability diagnostics cannot be allowed to compromise ingestion.
        return


def backfill_session_log(db: Session, session_id: str) -> int:
    """Create a diagnostic file for a trace that predates local diagnostics."""

    from voker_voice_api.models import Event
    from voker_voice_api.models import Session as VoiceSession

    session = db.get(VoiceSession, session_id)
    if session is None:
        raise ValueError("Session not found")
    write_session_log(
        str(session.id),
        "diagnostic_backfill_started",
        {
            "status": session.status,
            "started_at": session.started_at.isoformat(),
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        },
        external_session_id=session.external_session_id,
    )
    events = db.scalars(
        select(Event)
        .where(Event.session_id == session.id)
        .order_by(Event.occurred_at, Event.sequence, Event.id)
    ).all()
    for event in events:
        write_session_log(
            str(session.id),
            "event_backfilled_from_database",
            {
                "event": event.payload,
                "event_db_id": str(event.id),
                "received_at": event.received_at.isoformat() if event.received_at else None,
            },
            external_session_id=session.external_session_id,
        )
    return len(events)
