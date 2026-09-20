import pytest

from voker_voice import MemoryEventSink, VokerVoice, current_session


def test_session_and_span_emit_canonical_lifecycle_events() -> None:
    sink = MemoryEventSink()
    voker = VokerVoice(enabled=True, event_sink=sink)

    with voker.session(agent="support-agent", session_id="call-1") as call:
        with call.span("llm", provider="openrouter", model="test/model") as span:
            span.set_output({"message": "hello"})
            span.set_usage(input_tokens=4, output_tokens=2, total_tokens=6)

    assert [event["event_type"] for event in sink.events] == [
        "session.started",
        "llm.started",
        "llm.completed",
        "session.ended",
    ]
    assert sink.events[2]["usage"]["total_tokens"] == 6
    assert current_session() is None


def test_span_error_is_recorded_and_application_error_is_reraised() -> None:
    sink = MemoryEventSink()
    voker = VokerVoice(enabled=True, event_sink=sink)

    with pytest.raises(ValueError, match="planned failure"):
        with voker.session(agent="support-agent") as call:
            with call.tool("lookup", protocol="mcp", server="crm-mcp"):
                raise ValueError("planned failure")

    failed = [event for event in sink.events if event["event_type"] == "tool.error"]
    assert failed[0]["error"]["type"] == "ValueError"


def test_secret_fields_are_redacted_before_export() -> None:
    sink = MemoryEventSink()
    voker = VokerVoice(enabled=True, event_sink=sink)

    with voker.session(agent="support-agent", metadata={"api_key": "private"}) as call:
        call.emit("custom", status="ok", attributes={"authorization": "Bearer private"})

    assert sink.events[0]["attributes"]["api_key"] == "[REDACTED]"
    assert sink.events[1]["attributes"]["authorization"] == "[REDACTED]"
