"""Optional LiveKit AgentSession observer using public AgentSession events."""

from typing import Any

from voker_voice.context import VoiceSession


def observe(agent_session: Any, session: VoiceSession) -> None:
    """Attach non-invasive lifecycle listeners to a LiveKit AgentSession.

    The adapter relies only on the public ``on(event, callback)`` emitter API.
    """

    def emit(name: str, payload: Any, *, status: str = "ok") -> None:
        data = (
            payload.model_dump(mode="json")
            if hasattr(payload, "model_dump")
            else {"value": str(payload)}
        )
        kwargs: dict[str, Any] = {
            "status": status,
            "attributes": {"integration": "livekit", **data},
        }
        if status == "error":
            kwargs["error"] = {"type": "LiveKitError", "message": str(data), "retryable": False}
        session.emit(name, **kwargs)

    agent_session.on("user_input_transcribed", lambda event: emit("stt.completed", event))
    agent_session.on("conversation_item_added", lambda event: emit("conversation.item", event))
    agent_session.on("tool_execution_updated", lambda event: emit("tool.updated", event))
    agent_session.on("agent_false_interruption", lambda event: emit("voice.interruption", event))
    agent_session.on("overlapping_speech", lambda event: emit("voice.talk_over", event))
    agent_session.on("metrics_collected", lambda event: emit("voice.metrics", event))
    agent_session.on("error", lambda event: emit("livekit.error", event, status="error"))
    agent_session.on("close", lambda event: emit("livekit.session.closed", event))
