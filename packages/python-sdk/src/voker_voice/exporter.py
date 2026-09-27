from __future__ import annotations

import gzip
import hashlib
import json
import os
import queue
import random
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import httpx

from voker_voice.outbox import DurableEventOutbox


class EventSink(Protocol):
    def emit(self, event: dict[str, Any]) -> None: ...

    def flush(self, timeout: float | None = None) -> bool: ...

    def close(self) -> None: ...


class MemoryEventSink:
    """Test sink that records SDK events without network activity."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, event: dict[str, Any]) -> None:
        self.events.append(event)

    def flush(self, timeout: float | None = None) -> bool:
        return True

    def close(self) -> None:
        return None


def default_spool_path(endpoint: str, api_key: str) -> Path:
    configured = os.getenv("VOKER_OUTBOX_PATH")
    if configured:
        return Path(configured).expanduser()
    scope = hashlib.sha256(f"{endpoint}\0{api_key}".encode()).hexdigest()[:16]
    return Path.cwd() / ".voker" / f"outbox-{scope}.sqlite3"


class BackgroundExporter:
    """Durable fail-open exporter with exact, per-event acknowledgement."""

    _WAKE = object()
    _STOP = object()

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        max_queue_size: int = 100_000,
        batch_size: int = 100,
        flush_interval_seconds: float = 0.25,
        timeout_seconds: float = 10.0,
        shutdown_timeout_seconds: float = 2.0,
        max_retries: int = 1,
        transport: httpx.BaseTransport | None = None,
        diagnostic_hook: Callable[[str, list[dict[str, Any]], dict[str, Any]], None] | None = None,
        spool_path: str | Path | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/") + "/v1/events/batch"
        self.api_key = api_key
        self.batch_size = batch_size
        self.flush_interval_seconds = flush_interval_seconds
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.shutdown_timeout_seconds = shutdown_timeout_seconds
        self.transport = transport
        self.diagnostic_hook = diagnostic_hook
        resolved_spool: str | Path = (
            spool_path
            if spool_path is not None
            else ":memory:"
            if transport is not None
            else default_spool_path(endpoint, api_key)
        )
        self._outbox = DurableEventOutbox(resolved_spool, max_events=max_queue_size)
        self._queue: queue.Queue[object] = queue.Queue(maxsize=1)
        self._thread = threading.Thread(target=self._run, name="voker-voice-exporter", daemon=True)
        self._closed = False
        self.dropped_events = 0
        self.failed_batches = 0
        self._thread.start()

    def emit(self, event: dict[str, Any]) -> None:
        if self._closed:
            raise RuntimeError("cannot emit telemetry after the exporter is closed")
        try:
            inserted = self._outbox.append(event)
        except Exception as error:
            self.dropped_events += 1
            self._diagnose("export_dropped", [event], {"reason": str(error)})
            raise
        self._diagnose(
            "export_queued",
            [event],
            {"durable": True, "duplicate": not inserted, **self.health()},
        )
        self._wake()

    def _wake(self) -> None:
        try:
            self._queue.put_nowait(self._WAKE)
        except queue.Full:
            pass

    def flush(self, timeout: float | None = None) -> bool:
        deadline = time.monotonic() + (timeout if timeout is not None else self.timeout_seconds * 2)
        self._wake()
        while int(self.health()["pending_events"] or 0) > 0:
            if time.monotonic() >= deadline:
                return False
            self._wake()
            time.sleep(0.01)
        return True

    def close(self) -> None:
        if self._closed:
            return
        self.flush(timeout=self.shutdown_timeout_seconds)
        self._closed = True
        try:
            self._queue.put(self._STOP, timeout=0.1)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(self._STOP)
            except queue.Full:
                pass
        self._thread.join(timeout=max(1.0, self.shutdown_timeout_seconds))

    def health(self) -> dict[str, int | float | None | str]:
        return {
            **self._outbox.health(),
            "failed_batches": self.failed_batches,
            "dropped_events": self.dropped_events,
        }

    def _run(self) -> None:
        try:
            while True:
                try:
                    signal = self._queue.get(timeout=self.flush_interval_seconds)
                except queue.Empty:
                    signal = self._WAKE
                else:
                    self._queue.task_done()
                if signal is self._STOP:
                    return
                events = self._outbox.ready(limit=self.batch_size)
                if events:
                    self._deliver(events)
        finally:
            # The worker owns the SQLite connection lifetime. A network call
            # may still be finishing when close() reaches its bounded timeout;
            # closing from the caller would race the retry write and corrupt
            # shutdown diagnostics (the durable rows themselves remain safe).
            self._outbox.close()

    def _diagnose(
        self, stage: str, events: list[dict[str, Any]], data: dict[str, Any]
    ) -> None:
        if self.diagnostic_hook is None:
            return
        try:
            self.diagnostic_hook(stage, events, data)
        except Exception:
            return

    def _deliver(self, events: list[dict[str, Any]]) -> None:
        event_ids = {str(event["event_id"]) for event in events}
        payload = gzip.compress(
            json.dumps({"schema_version": "1.0", "events": events}, default=str).encode()
        )
        headers = {
            "Content-Encoding": "gzip",
            "Content-Type": "application/json",
            "X-Voker-Api-Key": self.api_key,
        }
        final_error = "delivery failed"
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                    response = client.post(self.endpoint, content=payload, headers=headers)
                response.raise_for_status()
                body: dict[str, Any] = {}
                try:
                    candidate = response.json()
                    if isinstance(candidate, dict):
                        body = candidate
                except ValueError:
                    pass
                items = body.get("items")
                if isinstance(items, list) and items:
                    acknowledged = {
                        str(item.get("event_id"))
                        for item in items
                        if isinstance(item, dict)
                        and item.get("status") in {"accepted", "duplicate"}
                    }
                    permanent = {
                        str(item.get("event_id"))
                        for item in items
                        if isinstance(item, dict)
                        and item.get("status") in {"rejected_permanent", "permanent_rejection"}
                    }
                elif int(body.get("rejected", 0) or 0) == 0:
                    acknowledged = set(event_ids)
                    permanent = set()
                else:
                    acknowledged = set()
                    permanent = set()
                self._outbox.acknowledge(acknowledged)
                self._outbox.quarantine(permanent, reason="server rejected event permanently")
                retryable = event_ids - acknowledged - permanent
                if retryable:
                    self._outbox.retry(
                        retryable,
                        reason="server did not acknowledge event",
                        delay_seconds=min(30.0, 0.1 * (2**attempt)),
                    )
                    self.failed_batches += 1
                self._diagnose(
                    "export_delivered",
                    events,
                    {
                        "attempt": attempt + 1,
                        "status_code": response.status_code,
                        "acknowledged": len(acknowledged),
                        "retryable": len(retryable),
                        "permanent_rejections": len(permanent),
                    },
                )
                return
            except (httpx.HTTPError, OSError) as error:
                final_error = str(error)
                self._diagnose(
                    "export_attempt_failed",
                    events,
                    {"attempt": attempt + 1, "error": final_error},
                )
            if attempt < self.max_retries:
                delay = 0.1 * (2**attempt)
                time.sleep(delay + random.uniform(0, delay * 0.25))
        self.failed_batches += 1
        self._outbox.retry(event_ids, reason=final_error, delay_seconds=0.1)
        self._diagnose(
            "export_failed",
            events,
            {"attempts": self.max_retries + 1, "error": final_error},
        )
