from datetime import UTC, datetime
from unittest.mock import MagicMock

from voker_voice_api.ingestion import ingest_batch, sse_payload
from voker_voice_api.schemas import CanonicalEvent


def raw_event(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_id": "evt-valid",
        "event_type": "llm.completed",
        "occurred_at": datetime.now(UTC).isoformat(),
        "external_session_id": "session-1",
        "trace_id": "trace-1",
        "status": "ok",
    }
    payload.update(overrides)
    return payload


def test_batch_keeps_valid_events_when_one_item_is_invalid(monkeypatch) -> None:
    db = MagicMock()
    context = MagicMock()
    monkeypatch.setattr("voker_voice_api.ingestion.persist_event", lambda *_: "accepted")

    result = ingest_batch(db, context, [raw_event(), {"event_id": "invalid"}])

    assert result.accepted == 1
    assert result.rejected == 1
    assert result.items[0].status == "accepted"
    assert result.items[1].status == "rejected"


def test_sse_payload_includes_trace_identity() -> None:
    event = CanonicalEvent.model_validate(raw_event())

    payload = sse_payload(event)

    assert "evt-valid" in payload
    assert "llm.completed" in payload
