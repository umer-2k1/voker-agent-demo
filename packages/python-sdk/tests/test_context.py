import asyncio
import time

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


def test_nested_spans_inherit_parent_turn_and_agent_run() -> None:
    sink = MemoryEventSink()
    client = VokerVoice(enabled=True, event_sink=sink)

    with client.session(agent="router", version="1.0") as call:
        with call.turn(speaker="user", transcript="Check my invoice"):
            with call.agent("billing", version="2.0"):
                with call.span("llm") as parent:
                    with call.tool("lookup_invoice", arguments={"invoice_id": "inv-1"}):
                        pass

    parent_start = next(event for event in sink.events if event["event_type"] == "llm.started")
    tool_start = next(event for event in sink.events if event["event_type"] == "tool.started")
    agent_start = next(event for event in sink.events if event["event_type"] == "agent.started")
    assert tool_start["parent_span_id"] == parent.span_id
    assert tool_start["turn_id"] == parent_start["turn_id"]
    assert tool_start["agent_run_id"] == agent_start["agent_run_id"]
    assert tool_start["agent"] == {"name": "billing", "version": "2.0"}
    assert tool_start["input"] == {"arguments": {"invoice_id": "inv-1"}}


def test_nested_agents_emit_parent_run_identity() -> None:
    sink = MemoryEventSink()
    client = VokerVoice(enabled=True, event_sink=sink)

    with client.session(agent="router") as call:
        with call.agent("triage") as triage:
            with call.agent("billing") as billing:
                pass

    starts = [event for event in sink.events if event["event_type"] == "agent.started"]
    assert starts[0]["agent_run_id"] == triage.run_id
    assert starts[1]["agent_run_id"] == billing.run_id
    assert starts[1]["parent_agent_run_id"] == triage.run_id


def test_mcp_protocol_error_becomes_failed_tool_span() -> None:
    sink = MemoryEventSink()
    client = VokerVoice(enabled=True, event_sink=sink)

    with client.session(agent="support") as call:
        with call.tool("lookup", protocol="mcp") as span:
            span.set_output({"isError": True, "message": "CRM unavailable"})

    failed = next(event for event in sink.events if event["event_type"] == "tool.error")
    assert failed["status"] == "error"
    assert failed["error"]["type"] == "MCPToolError"
    assert failed["error"]["message"] == "CRM unavailable"


@pytest.mark.asyncio
async def test_timeout_and_cancellation_keep_application_exception_semantics() -> None:
    sink = MemoryEventSink()
    client = VokerVoice(enabled=True, event_sink=sink)

    async with client.session(agent="support") as call:
        with pytest.raises(TimeoutError):
            async with call.span("llm"):
                raise TimeoutError("provider deadline")
        with pytest.raises(asyncio.CancelledError):
            async with call.span("tts"):
                raise asyncio.CancelledError("barge-in")

    statuses = {event["event_type"]: event["status"] for event in sink.events}
    assert statuses["llm.timeout"] == "timeout"
    assert statuses["tts.cancelled"] == "cancelled"


def test_span_can_explicitly_record_timeout_without_raising() -> None:
    sink = MemoryEventSink()
    client = VokerVoice(enabled=True, event_sink=sink)

    with client.session(agent="support") as call:
        with call.span("tool") as span:
            span.set_timeout("upstream deadline")

    event = next(event for event in sink.events if event["event_type"] == "tool.timeout")
    assert event["status"] == "timeout"
    assert event["error"]["message"] == "upstream deadline"


@pytest.mark.asyncio
async def test_context_propagates_to_child_tasks() -> None:
    sink = MemoryEventSink()
    client = VokerVoice(enabled=True, event_sink=sink)

    async with client.session(agent="support") as call:
        async with call.span("agent", name="parent") as parent:
            await asyncio.gather(
                child_span(call, "llm"),
                child_span(call, "tool"),
            )

    child_starts = [
        event
        for event in sink.events
        if event["event_type"] in {"llm.started", "tool.started"}
    ]
    assert {event["parent_span_id"] for event in child_starts} == {parent.span_id}


async def child_span(call, kind: str) -> None:
    async with call.span(kind):
        await asyncio.sleep(0)


def test_capture_controls_and_custom_redaction_hook_run_before_export() -> None:
    sink = MemoryEventSink()
    client = VokerVoice(
        enabled=True,
        event_sink=sink,
        capture_transcripts=False,
        capture_tool_data=False,
        redaction_hook=lambda value: {
            **value,
            "customer_id": "masked",
        }
        if isinstance(value, dict)
        else value,
    )

    with client.session(agent="support") as call:
        with call.turn(speaker="user", transcript="private words"):
            with call.tool("lookup", arguments={"customer_id": "cus-secret"}) as span:
                span.set_output({"customer_id": "cus-secret", "result": "ok"})

    turn = next(event for event in sink.events if event["event_type"] == "turn.started")
    tool_start = next(event for event in sink.events if event["event_type"] == "tool.started")
    tool_end = next(event for event in sink.events if event["event_type"] == "tool.completed")
    assert turn["attributes"]["transcript_omitted"] is True
    assert "input" not in tool_start
    assert "output" not in tool_end
    assert tool_end["attributes"]["tool_data_omitted"] is True


def test_oversized_event_is_replaced_with_deterministic_markers() -> None:
    sink = MemoryEventSink()
    client = VokerVoice(enabled=True, event_sink=sink, max_event_bytes=500)

    with client.session(agent="support") as call:
        call.emit("custom", status="ok", input={"text": "x" * 1000})

    custom = next(event for event in sink.events if event["event_type"] == "custom")
    assert custom["input"] == {"_voker_omitted": "event_size_limit"}
    assert custom["attributes"]["_voker_truncated"] is True


def test_environment_can_disable_export(monkeypatch) -> None:
    monkeypatch.setenv("VOKER_VOICE_ENABLED", "false")
    sink = MemoryEventSink()
    client = VokerVoice(api_key="configured", event_sink=sink)

    with client.session(agent="support"):
        pass

    assert client.enabled is False
    assert sink.events == []


def test_audio_metadata_capture_can_be_disabled() -> None:
    sink = MemoryEventSink()
    client = VokerVoice(enabled=True, event_sink=sink, capture_audio_metadata=False)

    with client.session(agent="support") as call:
        call.emit(
            "custom",
            status="ok",
            attributes={"audio_seconds": 3, "recording_url": "private", "safe": "kept"},
        )

    custom = next(event for event in sink.events if event["event_type"] == "custom")
    assert custom["attributes"] == {"safe": "kept", "audio_metadata_omitted": True}


def test_custom_events_require_a_namespace() -> None:
    sink = MemoryEventSink()
    client = VokerVoice(enabled=True, event_sink=sink)

    with client.session(agent="support") as call:
        call.custom("acme.routing", attributes={"route": "billing"})
        with pytest.raises(ValueError, match="namespaced"):
            call.custom("routing")

    custom = next(event for event in sink.events if event["event_type"] == "custom")
    assert custom["attributes"]["custom_name"] == "acme.routing"


@pytest.mark.asyncio
async def test_async_session_flush_does_not_block_event_loop() -> None:
    class SlowSink(MemoryEventSink):
        def flush(self, timeout: float | None = None) -> bool:
            time.sleep(0.05)
            return True

    ticked = False

    async def tick() -> None:
        nonlocal ticked
        await asyncio.sleep(0.01)
        ticked = True

    tick_task = asyncio.create_task(tick())
    async with VokerVoice(enabled=True, event_sink=SlowSink()).session(agent="support"):
        pass
    await tick_task
    assert ticked is True
