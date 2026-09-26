import gzip
import json
import queue

import httpx

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


def test_exporter_fails_open_when_endpoint_is_unavailable() -> None:
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
        assert exporter.flush(timeout=1)
        assert exporter.failed_batches == 1
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


def test_exporter_drops_events_when_bounded_queue_is_full() -> None:
    exporter = object.__new__(BackgroundExporter)
    exporter._closed = False
    exporter._queue = queue.Queue(maxsize=1)
    exporter.dropped_events = 0

    exporter.emit({"event_id": "evt_1"})
    exporter.emit({"event_id": "evt_2"})

    assert exporter._queue.qsize() == 1
    assert exporter.dropped_events == 1
