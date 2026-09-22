import asyncio
import atexit
import json
import logging
import os
from typing import Any

from voker_voice.context import VoiceSession
from voker_voice.exporter import BackgroundExporter, EventSink
from voker_voice.redaction import RedactionHook, redact

logger = logging.getLogger("voker_voice")


def environment_enabled() -> bool | None:
    value = os.getenv("VOKER_VOICE_ENABLED")
    if value is None:
        return None
    return value.strip().lower() not in {"0", "false", "no", "off"}


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
        capture_transcripts: bool = True,
        capture_tool_data: bool = True,
        capture_stacktraces: bool = False,
        capture_audio_metadata: bool = True,
        redaction_hook: RedactionHook | None = None,
        max_string_length: int = 10_000,
        max_collection_items: int = 100,
        max_event_bytes: int = 128_000,
        session_flush_timeout: float = 0.25,
        diagnostics: bool = False,
        event_sink: EventSink | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("VOKER_API_KEY")
        self.endpoint = endpoint or os.getenv("VOKER_VOICE_ENDPOINT") or "http://127.0.0.1:8001"
        configured_enabled = environment_enabled()
        self.enabled = (
            enabled
            if enabled is not None
            else configured_enabled
            if configured_enabled is not None
            else bool(self.api_key)
        )
        self.capture_inputs = capture_inputs
        self.capture_outputs = capture_outputs
        self.capture_transcripts = capture_transcripts
        self.capture_tool_data = capture_tool_data
        self.capture_stacktraces = capture_stacktraces
        self.capture_audio_metadata = capture_audio_metadata
        self.redaction_hook = redaction_hook
        self.max_string_length = max_string_length
        self.max_collection_items = max_collection_items
        self.max_event_bytes = max_event_bytes
        self.session_flush_timeout = session_flush_timeout
        self.diagnostics = diagnostics
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
        version: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VoiceSession:
        return VoiceSession(
            self,
            agent=agent,
            session_id=session_id,
            trace_id=trace_id,
            version=version,
            metadata=metadata,
        )

    def _emit(self, event: dict[str, Any]) -> None:
        if self.enabled and self._sink is not None:
            try:
                self._sink.emit(self._bound_event(event))
            except Exception:
                if self.diagnostics:
                    logger.exception("Voker Voice dropped an event after an exporter error")

    def _sanitize(self, value: Any) -> Any:
        try:
            candidate = self.redaction_hook(value) if self.redaction_hook is not None else value
        except Exception:
            candidate = value
            if self.diagnostics:
                logger.exception("Voker Voice redaction hook failed; default redaction was applied")
        return redact(
            candidate,
            max_string_length=self.max_string_length,
            max_collection_items=self.max_collection_items,
        )

    def _bound_event(self, event: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(event, default=str, separators=(",", ":")).encode()
        if len(encoded) <= self.max_event_bytes:
            return event
        bounded = dict(event)
        for field in ("input", "output"):
            if field in bounded:
                bounded[field] = {"_voker_omitted": "event_size_limit"}
        attributes = dict(bounded.get("attributes") or {})
        attributes["_voker_truncated"] = True
        attributes["_voker_original_bytes"] = len(encoded)
        bounded["attributes"] = attributes
        if len(json.dumps(bounded, default=str).encode()) > self.max_event_bytes:
            bounded["attributes"] = {
                "_voker_truncated": True,
                "_voker_original_bytes": len(encoded),
            }
        return bounded

    def flush(self, timeout: float | None = None) -> bool:
        if self._sink is None:
            return True
        try:
            delivered = self._sink.flush(timeout)
        except Exception:
            if self.diagnostics:
                logger.exception("Voker Voice exporter flush failed")
            return False
        if not delivered and self.diagnostics:
            logger.warning("Voker Voice exporter flush reached its timeout")
        return delivered

    async def aflush(self, timeout: float | None = None) -> bool:
        return await asyncio.to_thread(self.flush, timeout)

    def close(self) -> None:
        if self._sink is not None:
            try:
                self._sink.close()
            except Exception:
                if self.diagnostics:
                    logger.exception("Voker Voice exporter shutdown failed")

    async def aclose(self) -> None:
        await asyncio.to_thread(self.close)
