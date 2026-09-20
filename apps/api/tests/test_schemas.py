from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from voker_voice_api.schemas import CanonicalEvent, SpanStatus


def event_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_id": "evt_01",
        "event_type": "llm.completed",
        "occurred_at": datetime.now(UTC),
        "external_session_id": "call_123",
        "trace_id": "trc_01",
        "status": "ok",
    }
    payload.update(overrides)
    return payload


def test_accepts_canonical_event() -> None:
    event = CanonicalEvent.model_validate(event_payload())

    assert event.status == SpanStatus.OK
    assert event.schema_version == "1.0"


def test_requires_error_payload_for_error_status() -> None:
    with pytest.raises(ValidationError, match="error payload is required"):
        CanonicalEvent.model_validate(event_payload(status="error"))


def test_rejects_error_payload_on_success() -> None:
    with pytest.raises(ValidationError, match="status must be error"):
        CanonicalEvent.model_validate(
            event_payload(error={"type": "ValueError", "message": "bad input"})
        )
