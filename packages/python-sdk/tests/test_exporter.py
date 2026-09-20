import gzip
import json

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
