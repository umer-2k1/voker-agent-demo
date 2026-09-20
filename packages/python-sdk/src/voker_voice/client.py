import atexit
import os
from typing import Any

from voker_voice.context import VoiceSession
from voker_voice.exporter import BackgroundExporter, EventSink


class VokerVoice:
    """Fail-open Python instrumentation client for Voker Voice."""

    version = "0.1.0"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        endpoint: str | None = None,
        enabled: bool | None = None,
        capture_inputs: bool = True,
        capture_outputs: bool = True,
        event_sink: EventSink | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("VOKER_API_KEY")
        self.endpoint = endpoint or os.getenv("VOKER_VOICE_ENDPOINT", "http://127.0.0.1:8001")
        self.enabled = enabled if enabled is not None else bool(self.api_key)
        self.capture_inputs = capture_inputs
        self.capture_outputs = capture_outputs
        self._sink = event_sink
        if self._sink is None and self.enabled and self.api_key:
            self._sink = BackgroundExporter(endpoint=self.endpoint, api_key=self.api_key)
        atexit.register(self.close)

    def session(
        self,
        *,
        agent: str,
        session_id: str | None = None,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VoiceSession:
        return VoiceSession(
            self,
            agent=agent,
            session_id=session_id,
            trace_id=trace_id,
            metadata=metadata,
        )

    def _emit(self, event: dict[str, Any]) -> None:
        if self.enabled and self._sink is not None:
            self._sink.emit(event)

    def flush(self, timeout: float | None = None) -> bool:
        return self._sink.flush(timeout) if self._sink is not None else True

    def close(self) -> None:
        if self._sink is not None:
            self._sink.close()
