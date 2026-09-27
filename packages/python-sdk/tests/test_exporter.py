import gzip
import json
from pathlib import Path

import httpx
import pytest

from voker_voice.exporter import BackgroundExporter


def test_background_exporter_sends_gzip_batch_and_flush_waits_for_delivery() -> None:
    received: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(200, json={"accepted": 1, "duplicate": 0, "rejected": 0, "items": []})

    exporter = BackgroundExporter(
        endpoint="https://ingest.example",
        api_key="test-key",
        flush_interval_seconds=0.01,
        transport=httpx.MockTransport(handler),
    )
    try:
        exporter.emit({"event_id": "evt_1", "event_type": "session.started"})

        assert exporter.flush(timeout=1)
        assert len(received) == 1
        assert received[0].headers["content-encoding"] == "gzip"
        assert json.loads(gzip.decompress(received[0].content))["events"][0]["event_id"] == "evt_1"
    finally:
        exporter.close()


def test_exporter_retains_events_when_endpoint_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    exporter = BackgroundExporter(
        endpoint="https://ingest.example",
        api_key="test-key",
        flush_interval_seconds=0.01,
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    try:
        exporter.emit({"event_id": "evt_1", "event_type": "session.started"})
        assert exporter.flush(timeout=0.1) is False
        assert exporter.failed_batches >= 1
        assert exporter.health()["pending_events"] == 1
    finally:
        exporter.close()


def test_exporter_close_drains_terminal_events() -> None:
    received: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(200)

    exporter = BackgroundExporter(
        endpoint="https://ingest.example",
        api_key="test-key",
        flush_interval_seconds=0.01,
        transport=httpx.MockTransport(handler),
    )
    exporter.emit({"event_id": "evt_terminal", "event_type": "session.ended"})
    exporter.close()
    exporter._thread.join(timeout=1)

    assert exporter._thread.daemon is True
    assert not exporter._thread.is_alive()
    payload = json.loads(gzip.decompress(received[0].content))
    assert payload["events"][0]["event_type"] == "session.ended"


def test_exporter_keeps_running_when_a_provider_value_is_not_json_serializable() -> None:
    received: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(200)

    exporter = BackgroundExporter(
        endpoint="https://ingest.example",
        api_key="test-key",
        flush_interval_seconds=0.01,
        transport=httpx.MockTransport(handler),
    )
    try:
        exporter.emit({"event_id": "evt_1", "value": object()})
        assert exporter.flush(timeout=1)
        assert len(received) == 1
        assert exporter.failed_batches == 0
    finally:
        exporter.close()


def test_full_outbox_fails_visibly_instead_of_silently_dropping(
    tmp_path: Path,
) -> None:
    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    exporter = BackgroundExporter(
        endpoint="https://ingest.example",
        api_key="test-key",
        spool_path=tmp_path / "bounded.sqlite3",
        max_queue_size=1,
        max_retries=0,
        shutdown_timeout_seconds=0.01,
        transport=httpx.MockTransport(offline),
    )
    try:
        exporter.emit({"event_id": "evt_1"})
        with pytest.raises(RuntimeError, match="outbox is full"):
            exporter.emit({"event_id": "evt_2"})
        assert exporter.health()["pending_events"] == 1
        assert exporter.dropped_events == 1
    finally:
        exporter.close()


def test_failed_delivery_survives_restart_and_is_replayed(tmp_path: Path) -> None:
    spool_path = tmp_path / "outbox.sqlite3"

    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    first = BackgroundExporter(
        endpoint="https://ingest.example",
        api_key="test-key",
        spool_path=spool_path,
        flush_interval_seconds=0.01,
        max_retries=0,
        transport=httpx.MockTransport(offline),
    )
    first.emit({"event_id": "evt_1", "event_type": "user.message"})
    assert first.flush(timeout=0.1) is False
    assert first.health()["pending_events"] == 1
    first.close()

    delivered: list[str] = []

    def online(request: httpx.Request) -> httpx.Response:
        payload = json.loads(gzip.decompress(request.content))
        delivered.extend(event["event_id"] for event in payload["events"])
        return httpx.Response(
            200,
            json={
                "accepted": len(payload["events"]),
                "duplicate": 0,
                "rejected": 0,
                "items": [
                    {"event_id": event["event_id"], "status": "accepted"}
                    for event in payload["events"]
                ],
            },
        )

    second = BackgroundExporter(
        endpoint="https://ingest.example",
        api_key="test-key",
        spool_path=spool_path,
        flush_interval_seconds=0.01,
        transport=httpx.MockTransport(online),
    )
    try:
        assert second.flush(timeout=1) is True
        assert delivered == ["evt_1"]
        assert second.health()["pending_events"] == 0
    finally:
        second.close()


def test_exporter_removes_only_events_acknowledged_by_id(tmp_path: Path) -> None:
    spool_path = tmp_path / "partial-ack.sqlite3"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "accepted": 1,
                "duplicate": 0,
                "rejected": 1,
                "items": [
                    {"event_id": "evt_1", "status": "accepted"},
                    {"event_id": "evt_2", "status": "retryable"},
                ],
            },
        )

    exporter = BackgroundExporter(
        endpoint="https://ingest.example",
        api_key="test-key",
        spool_path=spool_path,
        batch_size=2,
        flush_interval_seconds=0.01,
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    try:
        exporter.emit({"event_id": "evt_1", "event_type": "session.started"})
        exporter.emit({"event_id": "evt_2", "event_type": "user.message"})
        assert exporter.flush(timeout=0.1) is False
        assert exporter.health()["pending_events"] == 1
    finally:
        exporter.close()


def test_exporter_rejects_emits_after_close_instead_of_silently_dropping() -> None:
    exporter = BackgroundExporter(
        endpoint="https://ingest.example",
        api_key="test-key",
        transport=httpx.MockTransport(lambda request: httpx.Response(200)),
    )
    exporter.close()

    with pytest.raises(RuntimeError, match="closed"):
        exporter.emit({"event_id": "evt_too_late"})
