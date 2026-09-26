import gzip
import json
import queue
import random
import threading
import time
from collections.abc import Callable, Iterable
from typing import Any, Protocol

import httpx


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


class BackgroundExporter:
    """Bounded, fail-open exporter that never sits in the provider request path."""

    _STOP = object()

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        max_queue_size: int = 2_000,
        batch_size: int = 50,
        flush_interval_seconds: float = 0.25,
        timeout_seconds: float = 10.0,
        shutdown_timeout_seconds: float = 2.0,
        max_retries: int = 0,
        transport: httpx.BaseTransport | None = None,
        diagnostic_hook: Callable[[str, list[dict[str, Any]], dict[str, Any]], None] | None = None,
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
        self._queue: queue.Queue[dict[str, Any] | object] = queue.Queue(maxsize=max_queue_size)
        self._thread = threading.Thread(target=self._run, name="voker-voice-exporter", daemon=True)
        self._closed = False
        self.dropped_events = 0
        self.failed_batches = 0
        self._thread.start()

    def emit(self, event: dict[str, Any]) -> None:
        if self._closed:
            return
        try:
            self._queue.put_nowait(event)
            self._diagnose("export_queued", [event], {"queue_size": self._queue.qsize()})
        except queue.Full:
            self.dropped_events += 1
            self._diagnose("export_dropped", [event], {"reason": "queue_full"})

    def flush(self, timeout: float | None = None) -> bool:
        deadline = time.monotonic() + (timeout if timeout is not None else self.timeout_seconds * 2)
        while self._queue.unfinished_tasks:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)
        return True

    def close(self) -> None:
        if self._closed:
            return
        # A terminal session event may be queued behind an in-flight batch. On
        # LiveKit shutdown there is no caller left to serve, so spend a bounded
        # window draining that terminal batch before the job process exits.
        self.flush(timeout=self.shutdown_timeout_seconds)
        self._closed = True
        try:
            self._queue.put_nowait(self._STOP)
        except queue.Full:
            pass

    def _run(self) -> None:
        batch: list[dict[str, Any]] = []
        while True:
            try:
                item = self._queue.get(timeout=self.flush_interval_seconds)
            except queue.Empty:
                if batch:
                    self._send_and_ack(batch)
                    batch = []
                continue
            if item is self._STOP:
                if batch:
                    self._send_and_ack(batch)
                self._queue.task_done()
                return
            batch.append(item)  # type: ignore[arg-type]
            while len(batch) < self.batch_size:
                try:
                    next_item = self._queue.get_nowait()
                except queue.Empty:
                    break
                if next_item is self._STOP:
                    self._queue.task_done()
                    self._send_and_ack(batch)
                    return
                batch.append(next_item)  # type: ignore[arg-type]
            if len(batch) >= self.batch_size:
                self._send_and_ack(batch)
                batch = []

    def _send_and_ack(self, events: list[dict[str, Any]]) -> None:
        try:
            self._send(events)
        except Exception:
            # Telemetry must never terminate the background exporter or affect
            # the application when a provider payload is unexpectedly shaped.
            self.failed_batches += 1
        finally:
            for _ in events:
                self._queue.task_done()

    def _diagnose(
        self, stage: str, events: list[dict[str, Any]], data: dict[str, Any]
    ) -> None:
        hook = getattr(self, "diagnostic_hook", None)
        if hook is None:
            return
        try:
            hook(stage, events, data)
        except Exception:
            return

    def _send(self, events: Iterable[dict[str, Any]]) -> None:
        try:
            event_list = list(events)
            payload = gzip.compress(
                json.dumps(
                    {"schema_version": "1.0", "events": event_list}, default=str
                ).encode()
            )
            headers = {
                "Content-Encoding": "gzip",
                "Content-Type": "application/json",
                "X-Voker-Api-Key": self.api_key,
            }
            for attempt in range(self.max_retries + 1):
                try:
                    with httpx.Client(
                        timeout=self.timeout_seconds, transport=self.transport
                    ) as client:
                        response = client.post(self.endpoint, content=payload, headers=headers)
                    if response.status_code < 500:
                        response.raise_for_status()
                        details: dict[str, Any] = {
                            "attempt": attempt + 1,
                            "status_code": response.status_code,
                        }
                        try:
                            body = response.json()
                            if isinstance(body, dict):
                                details.update(
                                    {
                                        key: body.get(key)
                                        for key in ("accepted", "duplicate", "rejected")
                                        if key in body
                                    }
                                )
                        except ValueError:
                            pass
                        self._diagnose("export_delivered", event_list, details)
                        return
                except (httpx.HTTPError, OSError) as error:
                    self._diagnose(
                        "export_attempt_failed",
                        event_list,
                        {"attempt": attempt + 1, "error": str(error)},
                    )
                if attempt < self.max_retries:
                    delay = 0.1 * (2**attempt)
                    time.sleep(delay + random.uniform(0, delay * 0.25))
            self.failed_batches += 1
            self._diagnose("export_failed", event_list, {"attempts": self.max_retries + 1})
        except Exception:
            self.failed_batches += 1
            self._diagnose(
                "export_failed", list(events), {"reason": "serialization_or_export_error"}
            )
