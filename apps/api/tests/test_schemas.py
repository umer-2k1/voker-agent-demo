import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from voker_voice_api.schemas import CanonicalEvent, SpanStatus

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


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
    with pytest.raises(ValidationError, match="requires error, cancelled, or timeout"):
        CanonicalEvent.model_validate(
            event_payload(error={"type": "ValueError", "message": "bad input"})
        )


def test_shared_valid_fixture_matches_json_schema_and_api_model() -> None:
    schema = json.loads(
        (REPOSITORY_ROOT / "packages/event-schema/canonical-event-1.0.json").read_text()
    )
    fixture = json.loads(
        (
            REPOSITORY_ROOT / "packages/event-schema/fixtures/valid/nested-voice-trace.json"
        ).read_text()
    )
    validator = Draft202012Validator(schema)
    for payload in fixture["events"]:
        validator.validate(payload)
        CanonicalEvent.model_validate(payload)


def test_shared_invalid_fixture_is_rejected_by_api_model() -> None:
    payload = json.loads(
        (
            REPOSITORY_ROOT / "packages/event-schema/fixtures/invalid/error-without-details.json"
        ).read_text()
    )
    with pytest.raises(ValidationError, match="error payload is required"):
        CanonicalEvent.model_validate(payload)
