"""Optional LiveKit AgentSession observer using public AgentSession events."""

from typing import Any

from voker_voice.context import VoiceSession


def observe(agent_session: Any, session: VoiceSession) -> None:
    """Attach non-invasive lifecycle listeners to a LiveKit AgentSession.

    The adapter relies only on the public ``on(event, callback)`` emitter API.
    """

    def event_data(payload: Any) -> dict[str, Any]:
        if hasattr(payload, "model_dump"):
            value = payload.model_dump(mode="json")
            return value if isinstance(value, dict) else {"value": value}
        if isinstance(payload, dict):
            return payload
        return {"value": str(payload)}

    def emit(name: str, payload: Any, *, status: str = "ok") -> None:
        data = event_data(payload)
        transcript = data.get("transcript") or data.get("text")
        speaker = data.get("speaker")
        attributes = {"integration": "livekit", **data}
        if isinstance(transcript, str):
            attributes["transcript"] = transcript
        if isinstance(speaker, str):
            attributes["speaker"] = speaker
        kwargs: dict[str, Any] = {
            "status": status,
            "attributes": attributes,
        }
        if name == "stt.completed" and isinstance(transcript, str):
            kwargs["input"] = {"text": transcript}
        if name == "tts.completed" and isinstance(transcript, str):
            kwargs["output"] = {"text": transcript}
        if status == "error":
            kwargs["error"] = {"type": "LiveKitError", "message": str(data), "retryable": False}
        session.emit(name, **kwargs)

    agent_session.on("agent_started", lambda event: emit("livekit.agent.started", event))
    agent_session.on("user_input_transcribed", lambda event: emit("stt.completed", event))
    agent_session.on("conversation_item_added", lambda event: emit("conversation.item", event))
    agent_session.on("tool_execution_updated", lambda event: emit("tool.updated", event))
    agent_session.on("agent_state_changed", lambda event: emit("livekit.agent.state", event))
    agent_session.on("tts_playback_started", lambda event: emit("tts.playback.started", event))
    agent_session.on("tts_playback_finished", lambda event: emit("tts.playback.completed", event))
    agent_session.on("agent_false_interruption", lambda event: emit("voice.interruption", event))
    agent_session.on("overlapping_speech", lambda event: emit("voice.talk_over", event))
    agent_session.on("metrics_collected", lambda event: emit("voice.metrics", event))
    agent_session.on("error", lambda event: emit("livekit.error", event, status="error"))
    agent_session.on("close", lambda event: emit("livekit.session.closed", event))
