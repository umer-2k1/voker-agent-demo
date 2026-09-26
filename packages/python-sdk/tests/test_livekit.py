from types import SimpleNamespace

import pytest

from voker_voice import MemoryEventSink, VokerVoice, observe_livekit
from voker_voice_api.schemas import CanonicalEvent


class FakeAgentSession:
    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}
        self.current_speech = None

    def on(self, name, callback) -> None:
        self.handlers[name] = callback

    def off(self, name, callback) -> None:
        if self.handlers.get(name) is callback:
            del self.handlers[name]

    def emit(self, name: str, event) -> None:
        callback = self.handlers[name]
        callback(event)  # type: ignore[operator]


def event_types(sink: MemoryEventSink) -> list[str]:
    return [event["event_type"] for event in sink.events]


def test_one_call_observer_owns_lifecycle_and_context_metadata() -> None:
    sink = MemoryEventSink()
    client = VokerVoice(event_sink=sink, enabled=True)
    fake = FakeAgentSession()
    participant = SimpleNamespace(identity="caller-1", sid="PA_1", kind="sip")
    room = SimpleNamespace(
        name="support-room",
        sid="RM_1",
        remote_participants={"caller-1": participant},
    )
    context = SimpleNamespace(room=room, job=lambda: SimpleNamespace(id="JOB_1"))

    observer = observe_livekit(
        fake,
        context=context,
        agent="support-agent",
        version="1.0",
        client=client,
    )

    assert observer.session.session_id == "support-room"
    started = sink.events[0]
    assert started["event_type"] == "session.started"
    assert started["attributes"]["livekit_room_sid"] == "RM_1"
    assert started["attributes"]["participants"][0]["identity"] == "caller-1"
    assert started["source"]["integration"] == "livekit"

    fake.emit(
        "close",
        {"created_at": 1_700_000_010.0, "reason": "participant_disconnected", "error": None},
    )
    assert event_types(sink)[-1] == "session.ended"
    assert sink.events[-1]["status"] == "ok"
    assert fake.handlers == {}


def test_observer_does_not_close_a_caller_owned_client() -> None:
    sink = MemoryEventSink()
    client = VokerVoice(event_sink=sink, enabled=True)
    fake = FakeAgentSession()
    observer = observe_livekit(fake, client=client, session_id="call-1")

    fake.emit("close", {"created_at": 100.0, "reason": "participant_disconnected"})

    assert observer.owns_client is False
    assert client._sink is sink


def test_livekit_context_omits_async_room_metadata() -> None:
    async def room_sid():
        return "RM_ASYNC"

    sink = MemoryEventSink()
    client = VokerVoice(event_sink=sink, enabled=True)
    fake = FakeAgentSession()
    room = SimpleNamespace(name="support-room", sid=room_sid(), remote_participants={})

    observe_livekit(fake, context=SimpleNamespace(room=room), client=client)

    assert sink.events[0]["attributes"]["livekit_room_sid"] is None


def test_livekit_maps_voice_pipeline_with_real_public_event_names() -> None:
    sink = MemoryEventSink()
    fake = FakeAgentSession()
    client = VokerVoice(event_sink=sink, enabled=True)
    observe_livekit(fake, agent="voice-router", client=client, session_id="call-1")

    expected_public_events = {
        "user_state_changed",
        "agent_state_changed",
        "user_input_transcribed",
        "user_transcription_timeout",
        "conversation_item_added",
        "function_tools_executed",
        "tool_execution_updated",
        "metrics_collected",
        "session_usage_updated",
        "speech_created",
        "agent_false_interruption",
        "overlapping_speech",
        "error",
        "close",
    }
    assert set(fake.handlers) == expected_public_events

    fake.emit(
        "user_state_changed",
        {
            "old_state": "listening",
            "new_state": "speaking",
            "created_at": 100.0,
        },
    )
    fake.emit(
        "user_input_transcribed",
        {
            "transcript": "check my order",
            "is_final": True,
            "item_id": "item-user",
            "speaker_id": "caller",
            "language": "en",
            "created_at": 101.0,
        },
    )
    fake.emit(
        "user_state_changed",
        {
            "old_state": "speaking",
            "new_state": "listening",
            "created_at": 101.2,
        },
    )
    fake.emit(
        "metrics_collected",
        {
            "metrics": {
                "type": "llm_metrics",
                "request_id": "req-llm",
                "timestamp": 102.0,
                "duration": 0.8,
                "ttft": 0.2,
                "cancelled": False,
                "prompt_tokens": 20,
                "completion_tokens": 5,
                "prompt_cached_tokens": 3,
                "total_tokens": 25,
                "metadata": {
                    "model_name": "gpt-test",
                    "model_provider": "openai",
                },
            }
        },
    )
    fake.emit(
        "tool_execution_updated",
        {
            "created_at": 102.1,
            "update": {
                "type": "tool_call_started",
                "function_call": {
                    "call_id": "call-tool",
                    "name": "lookup_order",
                    "arguments": '{"order_id":"123"}',
                },
            },
        },
    )
    fake.emit(
        "tool_execution_updated",
        {
            "created_at": 102.4,
            "update": {
                "type": "tool_call_ended",
                "call_id": "call-tool",
                "status": "done",
                "message": "shipped",
            },
        },
    )
    speech = {"id": "speech-1", "interrupted": False}
    fake.current_speech = speech
    fake.emit(
        "speech_created",
        {
            "created_at": 102.5,
            "speech_handle": speech,
            "source": "generate_reply",
            "user_initiated": False,
        },
    )
    fake.emit(
        "metrics_collected",
        {
            "metrics": {
                "type": "tts_metrics",
                "request_id": "req-tts",
                "speech_id": "speech-1",
                "timestamp": 103.0,
                "duration": 0.4,
                "ttfb": 0.1,
                "cancelled": False,
                "audio_duration": 1.5,
                "characters_count": 16,
                "input_tokens": 0,
                "output_tokens": 0,
                "metadata": {
                    "model_name": "sonic",
                    "model_provider": "cartesia",
                },
            }
        },
    )
    fake.emit(
        "conversation_item_added",
        {
            "created_at": 103.1,
            "item": {
                "type": "message",
                "id": "item-agent",
                "role": "assistant",
                "content": ["Your order shipped"],
                "interrupted": False,
            },
        },
    )
    fake.emit(
        "agent_state_changed",
        {"old_state": "thinking", "new_state": "speaking", "created_at": 103.2},
    )
    fake.emit(
        "agent_state_changed",
        {"old_state": "speaking", "new_state": "listening", "created_at": 104.7},
    )
    fake.emit("close", {"created_at": 105.0, "reason": "task_completed", "error": None})

    types = event_types(sink)
    for required in (
        "speech.started",
        "speech.stopped",
        "stt.started",
        "stt.final",
        "stt.completed",
        "llm.started",
        "llm.first_token",
        "llm.completed",
        "tool.started",
        "tool.completed",
        "tts.started",
        "tts.first_audio",
        "tts.completed",
        "playback.started",
        "playback.completed",
        "turn.completed",
        "session.ended",
    ):
        assert required in types

    llm = next(event for event in sink.events if event["event_type"] == "llm.completed")
    assert llm["source"]["provider"] == "openai"
    assert llm["attributes"]["model"] == "gpt-test"
    assert llm["attributes"]["ttft_ms"] == 200
    assert llm["duration_ms"] == 800
    assert llm["usage"]["input_tokens"] == 20
    assert llm["usage"]["output_tokens"] == 5

    tool_start = next(event for event in sink.events if event["event_type"] == "tool.started")
    tool_end = next(event for event in sink.events if event["event_type"] == "tool.completed")
    assert tool_start["span_id"] == tool_end["span_id"]
    assert tool_start["input"]["arguments"] == {"order_id": "123"}
    assert tool_end["output"] == {"result": "shipped"}

    turn_ids = {
        event["turn_id"]
        for event in sink.events
        if event["event_type"]
        in {
            "stt.completed",
            "llm.completed",
            "tool.completed",
            "tts.completed",
            "playback.completed",
        }
    }
    assert len(turn_ids) == 1
    run_ids = {
        event["agent_run_id"]
        for event in sink.events
        if event["event_type"] in {"llm.completed", "tool.completed", "tts.completed"}
    }
    assert len(run_ids) == 1
    for event in sink.events:
        CanonicalEvent.model_validate(event)


def test_assistant_conversation_item_uses_a_distinct_agent_transcript_turn() -> None:
    sink = MemoryEventSink()
    fake = FakeAgentSession()
    client = VokerVoice(event_sink=sink, enabled=True)
    observe_livekit(fake, agent="voice-router", client=client, session_id="call-1")

    fake.emit(
        "user_state_changed",
        {"old_state": "listening", "new_state": "speaking", "created_at": 100.0},
    )
    user_turn_id = next(event["turn_id"] for event in sink.events if event["event_type"] == "turn.started")
    fake.emit(
        "conversation_item_added",
        {
            "created_at": 101.0,
            "item": {
                "type": "message",
                "id": "assistant-1",
                "role": "assistant",
                "content": ["Your appointment is booked."],
            },
        },
    )

    assistant_message = next(event for event in sink.events if event["event_type"] == "assistant.message")
    assert assistant_message["turn_id"] != user_turn_id
    assert assistant_message["attributes"]["speaker"] == "agent"
    assert assistant_message["attributes"]["transcript"] == "Your appointment is booked."


@pytest.mark.asyncio
async def test_livekit_context_drains_telemetry_after_close_not_inside_close_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink = MemoryEventSink()
    client = VokerVoice(event_sink=sink, enabled=True)
    fake = FakeAgentSession()
    callbacks = []
    context = SimpleNamespace(
        room=SimpleNamespace(name="support-room", sid="RM_1", remote_participants={}),
        add_shutdown_callback=callbacks.append,
    )
    observer = observe_livekit(fake, context=context, client=client)
    delivered: list[dict] = []
    monkeypatch.setattr(
        client,
        "deliver_terminal_event",
        lambda event, *, timeout_seconds: delivered.append(event) or True,
    )

    fake.emit("close", {"created_at": 100.0, "reason": "participant_disconnected"})

    assert len(callbacks) == 1
    assert observer.owns_client is False
    assert event_types(sink)[-1] == "session.ended"
    await callbacks[0]()
    assert delivered == [sink.events[-1]]


def test_false_interruption_is_not_reported_as_real_interruption() -> None:
    sink = MemoryEventSink()
    fake = FakeAgentSession()
    client = VokerVoice(event_sink=sink, enabled=True)
    observer = observe_livekit(fake, agent="agent", client=client)

    fake.emit(
        "agent_false_interruption",
        {"resumed": True, "created_at": 100.0},
    )
    observer.close()

    assert "voice.interruption" not in event_types(sink)
    event = next(
        event
        for event in sink.events
        if event.get("attributes", {}).get("custom_name") == "livekit.false_interruption"
    )
    assert event["event_type"] == "custom"


def test_overlap_and_user_speech_during_playback_are_evidence_backed() -> None:
    sink = MemoryEventSink()
    fake = FakeAgentSession()
    client = VokerVoice(event_sink=sink, enabled=True)
    observe_livekit(fake, agent="agent", client=client)
    speech = {"id": "speech-2", "interrupted": False}
    fake.current_speech = speech
    fake.emit(
        "speech_created",
        {
            "created_at": 10.0,
            "speech_handle": speech,
            "source": "generate_reply",
            "user_initiated": False,
        },
    )
    fake.emit(
        "agent_state_changed",
        {"old_state": "thinking", "new_state": "speaking", "created_at": 10.1},
    )
    fake.emit(
        "user_state_changed",
        {"old_state": "listening", "new_state": "speaking", "created_at": 10.2},
    )
    fake.emit(
        "overlapping_speech",
        {
            "created_at": 10.3,
            "detected_at": 10.3,
            "overlap_started_at": 10.2,
            "is_interruption": True,
            "detection_delay": 0.1,
        },
    )
    fake.emit(
        "agent_state_changed",
        {"old_state": "speaking", "new_state": "listening", "created_at": 10.5},
    )

    interruptions = [event for event in sink.events if event["event_type"] == "voice.interruption"]
    assert len(interruptions) == 1
    assert interruptions[0]["attributes"]["evidence"] == "user_speech_during_agent_playback"
    talk_over = next(event for event in sink.events if event["event_type"] == "voice.talk_over")
    assert talk_over["attributes"]["evidence"] == "livekit.overlapping_speech"
    assert talk_over["attributes"]["overlap_duration_ms"] == 100
    assert "playback.interrupted" in event_types(sink)


def test_tool_error_provider_error_and_semantic_handoff_are_preserved() -> None:
    sink = MemoryEventSink()
    fake = FakeAgentSession()
    client = VokerVoice(event_sink=sink, enabled=True)
    observe_livekit(fake, agent="triage-agent", version="v1", client=client)

    fake.emit(
        "function_tools_executed",
        {
            "created_at": 20.0,
            "function_calls": [
                {
                    "id": "item-call",
                    "call_id": "failed-call",
                    "name": "billing_lookup",
                    "arguments": '{"account":"A1"}',
                }
            ],
            "function_call_outputs": [
                {
                    "call_id": "failed-call",
                    "name": "billing_lookup",
                    "output": "provider unavailable",
                    "is_error": True,
                }
            ],
        },
    )
    fake.emit(
        "error",
        {
            "created_at": 20.1,
            "source": {"provider": "openai", "model": "gpt-test"},
            "error": {
                "type": "LLMError",
                "message": "rate limited",
                "request_id": "req-error",
                "recoverable": True,
            },
        },
    )
    fake.emit(
        "conversation_item_added",
        {
            "created_at": 20.2,
            "item": {
                "type": "agent_handoff",
                "id": "handoff-1",
                "old_agent_id": "triage-agent",
                "new_agent_id": "billing-agent",
            },
        },
    )

    tool_error = next(event for event in sink.events if event["event_type"] == "tool.error")
    assert tool_error["status"] == "error"
    assert tool_error["error"]["message"] == "provider unavailable"
    llm_error = next(event for event in sink.events if event["event_type"] == "llm.error")
    assert llm_error["source"]["provider"] == "openai"
    assert llm_error["error"]["retryable"] is True
    handoff = next(event for event in sink.events if event["event_type"] == "agent.handoff")
    child = [event for event in sink.events if event["event_type"] == "agent.started"][-1]
    assert handoff["attributes"]["to_agent"] == "billing-agent"
    assert child["parent_agent_run_id"] == handoff["agent_run_id"]


def test_existing_voice_session_remains_backward_compatible() -> None:
    sink = MemoryEventSink()
    fake = FakeAgentSession()
    with VokerVoice(event_sink=sink, enabled=True).session(
        agent="existing",
        session_id="existing-call",
    ) as session:
        observer = observe_livekit(fake, session)
        fake.emit(
            "user_input_transcribed",
            {"transcript": "hello", "is_final": True, "created_at": 1.0},
        )
        observer.close()

    assert event_types(sink).count("session.started") == 1
    assert event_types(sink).count("session.ended") == 1
    stt = next(event for event in sink.events if event["event_type"] == "stt.completed")
    assert stt["output"] == {"text": "hello"}


@pytest.mark.asyncio
async def test_adapter_accepts_livekit_public_event_models() -> None:
    pytest.importorskip("livekit.agents")
    from livekit.agents import AgentSession
    from livekit.agents.metrics import LLMMetrics
    from livekit.agents.voice import (
        AgentStateChangedEvent,
        MetricsCollectedEvent,
        UserInputTranscribedEvent,
        UserStateChangedEvent,
    )

    sink = MemoryEventSink()
    livekit_session = AgentSession()
    observer = observe_livekit(
        livekit_session,
        agent="public-api-agent",
        client=VokerVoice(event_sink=sink, enabled=True),
    )
    livekit_session.emit(
        "user_state_changed",
        UserStateChangedEvent(old_state="listening", new_state="speaking"),
    )
    livekit_session.emit(
        "user_input_transcribed",
        UserInputTranscribedEvent(
            transcript="public event",
            is_final=True,
            item_id="item-public",
        ),
    )
    livekit_session.emit(
        "metrics_collected",
        MetricsCollectedEvent(
            metrics=LLMMetrics(
                label="openai.LLM",
                request_id="req-public",
                timestamp=1_700_000_000.0,
                duration=0.5,
                ttft=0.1,
                cancelled=False,
                completion_tokens=4,
                prompt_tokens=8,
                prompt_cached_tokens=0,
                total_tokens=12,
                tokens_per_second=8,
            )
        ),
    )
    livekit_session.emit(
        "agent_state_changed",
        AgentStateChangedEvent(old_state="thinking", new_state="speaking"),
    )
    livekit_session.emit(
        "agent_state_changed",
        AgentStateChangedEvent(old_state="speaking", new_state="listening"),
    )
    observer.close()

    assert "stt.completed" in event_types(sink)
    assert "llm.completed" in event_types(sink)
    assert "playback.completed" in event_types(sink)


def test_livekit_observer_is_fail_open_when_exporter_is_unavailable() -> None:
    class FailingSink:
        def emit(self, _event) -> None:
            raise OSError("collector unavailable")

        def flush(self, _timeout=None) -> bool:
            raise TimeoutError("collector unavailable")

        def close(self) -> None:
            return None

    fake = FakeAgentSession()
    observer = observe_livekit(
        fake,
        agent="fail-open-agent",
        client=VokerVoice(event_sink=FailingSink(), enabled=True),
    )

    fake.emit(
        "user_input_transcribed",
        {"transcript": "still works", "is_final": True, "created_at": 1.0},
    )
    fake.emit("close", {"created_at": 2.0, "reason": "task_completed", "error": None})
    assert observer.session.session_id
