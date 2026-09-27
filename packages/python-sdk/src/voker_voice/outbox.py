from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class DurableEventOutbox:
    """Persistent at-least-once event buffer backed by SQLite WAL."""

    def __init__(self, path: str | Path, *, max_events: int = 100_000) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.max_events = max_events
        self._lock = threading.RLock()
        self._count = 0
        self._connection = sqlite3.connect(
            self.path, timeout=10, check_same_thread=False, isolation_level=None
        )
        with self._lock:
            if self.path != ":memory:":
                self._connection.execute("PRAGMA journal_mode=WAL")
                # NORMAL + WAL keeps transactions crash-safe for the process while
                # avoiding an fsync on every append. `synchronous=FULL` made each
                # emit block the caller's event loop (~100ms watchdog stalls on
                # the LiveKit agent loop); NORMAL removes that fsync from the hot
                # path. Only an OS/power failure can lose the last commits.
                self._connection.execute("PRAGMA synchronous=NORMAL")
            self._connection.execute("PRAGMA busy_timeout=10000")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS outbox_events (
                    event_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL DEFAULT 0,
                    last_error TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_outbox_ready
                    ON outbox_events(next_attempt_at, created_at);
                CREATE TABLE IF NOT EXISTS outbox_dead_letters (
                    event_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    quarantined_at REAL NOT NULL
                );
                """
            )
            # Track the row count in memory: a per-append SELECT count(*) is a
            # full-table scan that (with a growing outbox) stalled the caller's
            # event loop. The cap is a safety bound, not an exact invariant.
            self._count = int(
                self._connection.execute("SELECT count(*) FROM outbox_events").fetchone()[0]
            )

    def append(self, event: dict[str, Any]) -> bool:
        event_id = str(event.get("event_id") or "")
        if not event_id:
            raise ValueError("outbox events require a stable event_id")
        payload = json.dumps(event, default=str, separators=(",", ":"))
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT 1 FROM outbox_events WHERE event_id = ?", (event_id,)
            ).fetchone()
            if existing is not None:
                return False
            if self._count >= self.max_events:
                raise RuntimeError(f"durable event outbox is full ({self.max_events} events)")
            self._connection.execute(
                """
                INSERT INTO outbox_events (
                    event_id, payload, created_at, attempts, next_attempt_at
                ) VALUES (?, ?, ?, 0, 0)
                """,
                (event_id, payload, time.time()),
            )
            self._count += 1
        return True

    def ready(self, *, limit: int, now: float | None = None) -> list[dict[str, Any]]:
        current = time.time() if now is None else now
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT payload FROM outbox_events
                WHERE next_attempt_at <= ?
                ORDER BY created_at, event_id LIMIT ?
                """,
                (current, limit),
            ).fetchall()
        return [json.loads(str(row[0])) for row in rows]

    def acknowledge(self, event_ids: set[str]) -> None:
        if not event_ids:
            return
        placeholders = ",".join("?" for _ in event_ids)
        with self._lock, self._connection:
            self._connection.execute(
                f"DELETE FROM outbox_events WHERE event_id IN ({placeholders})",
                tuple(event_ids),
            )
            self._count = max(0, self._count - len(event_ids))

    def retry(
        self, event_ids: set[str], *, reason: str, delay_seconds: float
    ) -> None:
        if not event_ids:
            return
        placeholders = ",".join("?" for _ in event_ids)
        values: tuple[Any, ...] = (
            time.time() + max(0.0, delay_seconds),
            reason[:2_000],
            *event_ids,
        )
        with self._lock, self._connection:
            self._connection.execute(
                f"""
                UPDATE outbox_events
                SET attempts = attempts + 1,
                    next_attempt_at = ?,
                    last_error = ?
                WHERE event_id IN ({placeholders})
                """,
                values,
            )

    def quarantine(self, event_ids: set[str], *, reason: str) -> None:
        if not event_ids:
            return
        placeholders = ",".join("?" for _ in event_ids)
        with self._lock, self._connection:
            rows = self._connection.execute(
                f"SELECT event_id, payload FROM outbox_events WHERE event_id IN ({placeholders})",
                tuple(event_ids),
            ).fetchall()
            self._connection.executemany(
                """
                INSERT OR REPLACE INTO outbox_dead_letters (
                    event_id, payload, reason, quarantined_at
                ) VALUES (?, ?, ?, ?)
                """,
                [(row[0], row[1], reason[:2_000], time.time()) for row in rows],
            )
            self._connection.execute(
                f"DELETE FROM outbox_events WHERE event_id IN ({placeholders})",
                tuple(event_ids),
            )
            self._count = max(0, self._count - len(event_ids))

    def health(self) -> dict[str, int | float | None | str]:
        with self._lock:
            pending, oldest = self._connection.execute(
                "SELECT count(*), min(created_at) FROM outbox_events"
            ).fetchone()
            dead_letters = self._connection.execute(
                "SELECT count(*) FROM outbox_dead_letters"
            ).fetchone()[0]
        return {
            "path": self.path,
            "pending_events": int(pending),
            "dead_letter_events": int(dead_letters),
            "oldest_pending_age_seconds": (
                max(0.0, time.time() - float(oldest)) if oldest is not None else None
            ),
        }

    def close(self) -> None:
        with self._lock:
            self._connection.close()
