"""Local, append-only SDK delivery diagnostics for session investigations."""

from __future__ import annotations

import json
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|password|secret|access[_-]?token|refresh[_-]?token)",
    re.I,
)


class SessionDiagnosticWriter:
    """Write redacted JSONL alongside a local voice-agent run.

    The log is deliberately best-effort: tracing must continue even if the
    filesystem is read-only or a user has disabled local diagnostics.
    """

    def __init__(self, directory: str | Path | None) -> None:
        self.directory = Path(directory) if directory else None
        self._lock = threading.Lock()
        # Directory setup is a one-time best-effort operation. Calling mkdir
        # for every event runs synchronously on LiveKit callbacks and showed
        # up as audio-loop stalls in the real call logs.
        if self.directory is not None:
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
            except OSError:
                self.directory = None

    @staticmethod
    def _safe_value(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): "[REDACTED]"
                if _SENSITIVE_KEY.search(str(key))
                else SessionDiagnosticWriter._safe_value(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [SessionDiagnosticWriter._safe_value(item) for item in value]
        return value

    def write(self, event: dict[str, Any], stage: str, data: dict[str, Any] | None = None) -> None:
        if self.directory is None:
            return
        session_id = str(event.get("external_session_id") or "unknown-session")
        safe_id = _SAFE_FILENAME.sub("_", session_id).strip("._") or "unknown-session"
        record: dict[str, Any] = {
            "logged_at": datetime.now(UTC).isoformat(),
            "stage": stage,
            "external_session_id": session_id,
            "event_id": event.get("event_id"),
            "event_type": event.get("event_type"),
        }
        if stage == "sdk_event_emitted":
            record["event"] = self._safe_value(event)
        if data:
            record["data"] = self._safe_value(data)
        try:
            with self._lock, (self.directory / f"{safe_id}.sdk.jsonl").open(
                "a", encoding="utf-8"
            ) as handle:
                handle.write(json.dumps(record, default=str, separators=(",", ":")) + "\n")
        except OSError:
            return
