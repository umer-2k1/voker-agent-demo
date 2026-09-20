from voker_voice import MemoryEventSink, VokerVoice, observe_livekit


class FakeAgentSession:
    def __init__(self) -> None:
        self.handlers = {}

    def on(self, name, callback):
        self.handlers[name] = callback


def test_livekit_observer_uses_public_events() -> None:
    sink = MemoryEventSink()
    fake = FakeAgentSession()
    with VokerVoice(event_sink=sink, enabled=True).session(agent="livekit") as session:
        observe_livekit(fake, session)
        fake.handlers["user_input_transcribed"]({"transcript": "hello"})
        fake.handlers["agent_false_interruption"]({"reason": "barge-in"})
    assert any(event["event_type"] == "stt.completed" for event in sink.events)
    assert any(event["event_type"] == "voice.interruption" for event in sink.events)
    stt_event = next(event for event in sink.events if event["event_type"] == "stt.completed")
    assert stt_event["attributes"]["transcript"] == "hello"
    assert stt_event["input"] == {"text": "hello"}
    assert "tts_playback_finished" in fake.handlers
