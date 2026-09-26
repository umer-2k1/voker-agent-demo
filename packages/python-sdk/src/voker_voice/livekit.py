"""LiveKit Agents adapter built only on public ``AgentSession`` events.

LiveKit remains an optional dependency. This module deliberately uses structural
typing so importing :mod:`voker_voice` never imports LiveKit itself.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from voker_voice.client import VokerVoice
from voker_voice.context import VoiceSession, new_id

logger = logging.getLogger("voker_voice.livekit")


def _value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _data(value: Any) -> dict[str, Any]:
    """Produce a serializable view without retaining audio samples."""

    if value is None:
        return {}
    if isinstance(value, dict):
        result = dict(value)
    elif hasattr(value, "model_dump"):
        try:
            result = value.model_dump(
                mode="json",
                exclude={"speech_input", "probabilities", "speech_handle"},
            )
        except Exception:
            result = value.model_dump(exclude={"speech_input", "probabilities", "speech_handle"})
    elif hasattr(value, "__dict__"):
        result = {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
            and key not in {"speech_input", "probabilities", "speech_handle"}
        }
    else:
        return {"value": str(value)}
    return result if isinstance(result, dict) else {"value": str(result)}


def _occurred_at(value: Any = None) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    return datetime.now(UTC)


def _external_id(prefix: str, value: Any = None) -> str:
    if value is None or str(value) == "":
        return new_id(prefix)
    digest = hashlib.blake2s(str(value).encode(), digest_size=12).hexdigest()
    return f"{prefix}_{digest}"


def _json_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {"raw": value}
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    return {"value": value}


def _context_metadata(context: Any) -> tuple[str | None, dict[str, Any]]:
    if context is None:
        return None, {"integration": "livekit", "transport": "livekit"}
    room = _value(context, "room")
    room_name = _context_value(_value(room, "name"))
    room_sid = _context_value(_value(room, "sid"))
    metadata: dict[str, Any] = {
        "integration": "livekit",
        "transport": "livekit",
        "livekit_room_name": room_name,
        "livekit_room_sid": room_sid,
    }
    participants = _value(room, "remote_participants", {}) or {}
    values = participants.values() if isinstance(participants, dict) else participants
    participant_rows = []
    for participant in values:
        participant_rows.append(
            {
                "identity": _context_value(_value(participant, "identity")),
                "sid": _context_value(_value(participant, "sid")),
                "kind": str(_context_value(_value(participant, "kind", ""))) or None,
            }
        )
    if participant_rows:
        metadata["participants"] = participant_rows
    job = _value(context, "job")
    if callable(job):
        try:
            job = job()
        except Exception:
            job = None
    job_id = _context_value(_value(job, "id"))
    if job_id:
        metadata["livekit_job_id"] = job_id
    inferred_id = str(room_name or room_sid) if room_name or room_sid else None
    return inferred_id, metadata


def _context_value(value: Any) -> Any:
    """Keep context metadata synchronous and JSON-safe.

    LiveKit 1.8 exposes some room fields as async properties.  The observer
    cannot await them while attaching synchronously, so omit them rather than
    putting a coroutine into the SDK export queue.
    """

    if inspect.isawaitable(value):
        close = getattr(value, "close", None)
        if callable(close):
            close()
        return None
    if callable(value):
        return None
    return value


class LiveKitObserver:
    """Own and translate the lifecycle of one observed LiveKit ``AgentSession``."""

    def __init__(
        self,
        agent_session: Any,
        session: VoiceSession,
        *,
        owns_session: bool,
        owns_client: bool,
        agent: str,
        version: str | None,
    ) -> None:
        self.agent_session = agent_session
        self.session = session
        self.owns_session = owns_session
        self.owns_client = owns_client
        self.agent_name = agent
        self.agent_version = version
        self._listeners: list[tuple[str, Callable[[Any], None]]] = []
        self._closed = False
        self._turn_id: str | None = None
        self._turn_has_assistant = False
        self._stt_span_id: str | None = None
        self._stt_started_at: datetime | None = None
        self._agent_run_id = _external_id("run", f"root:{agent}:{session.session_id}")
        self._agent_state = "initializing"
        self._user_state = "listening"
        self._active_speech: Any = None
        self._playback_span_id: str | None = None
        self._playback_started_at: datetime | None = None
        self._playback_interrupted = False
        self._span_started: set[str] = set()
        self._tts_spans: dict[str, str] = {}
        self._tool_runs: dict[str, tuple[str, datetime, str, dict[str, Any]]] = {}
        self._completed_tools: set[str] = set()
        self._latest_session_usage: dict[str, Any] | None = None
        self._terminal_event: dict[str, Any] | None = None

        if self.owns_session:
            self.session.emit(
                "session.started",
                status="ok",
                source={"integration": "livekit"},
                attributes=self.session.metadata,
            )
        self._emit(
            "agent.started",
            status="unset",
            agent_run_id=self._agent_run_id,
            attributes={"semantic_agent": self.agent_name, "integration": "livekit"},
        )
        self._attach()

    def _attach(self) -> None:
        listeners = {
            "user_state_changed": self._on_user_state,
            "agent_state_changed": self._on_agent_state,
            "user_input_transcribed": self._on_transcript,
            "user_transcription_timeout": self._on_transcription_timeout,
            "conversation_item_added": self._on_conversation_item,
            "function_tools_executed": self._on_tools_executed,
            "tool_execution_updated": self._on_tool_update,
            "metrics_collected": self._on_metrics,
            "session_usage_updated": self._on_session_usage,
            "speech_created": self._on_speech_created,
            "agent_false_interruption": self._on_false_interruption,
            "overlapping_speech": self._on_overlapping_speech,
            "error": self._on_error,
            "close": self._on_close,
        }
        for name, callback in listeners.items():
            safe_callback = self._safe(callback)
            self.agent_session.on(name, safe_callback)
            self._listeners.append((name, safe_callback))

    def _safe(self, callback: Callable[[Any], None]) -> Callable[[Any], None]:
        def wrapped(event: Any) -> None:
            try:
                callback(event)
            except Exception:
                if self.session.client.diagnostics:
                    logger.exception("Voker Voice ignored a LiveKit adapter callback failure")

        return wrapped

    def _emit(
        self, event_type: str, *, provider: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        source = {"integration": "livekit"}
        if provider:
            source["provider"] = provider
        return self.session.emit(
            event_type,
            source=source,
            turn_id=kwargs.pop("turn_id", self._turn_id),
            agent_run_id=kwargs.pop("agent_run_id", self._agent_run_id),
            agent_name=kwargs.pop("agent_name", self.agent_name),
            agent_version=kwargs.pop("agent_version", self.agent_version),
            **kwargs,
        )

    def _ensure_turn(self, occurred_at: datetime) -> str:
        if self._turn_id is not None:
            return self._turn_id
        self._turn_id = new_id("turn")
        self._turn_has_assistant = False
        self._stt_span_id = _external_id("spn", f"stt:{self._turn_id}")
        self._emit(
            "turn.started",
            occurred_at=occurred_at,
            status="unset",
            attributes={"speaker": "user", "integration": "livekit"},
        )
        return self._turn_id

    def _finish_turn(self, occurred_at: datetime, *, abandoned: bool = False) -> None:
        if self._turn_id is None:
            return
        self._emit(
            "turn.abandoned" if abandoned else "turn.completed",
            occurred_at=occurred_at,
            status="cancelled" if abandoned else "ok",
            attributes={"speaker": "user", "integration": "livekit"},
        )
        self._turn_id = None
        self._turn_has_assistant = False
        self._stt_span_id = None
        self._stt_started_at = None

    def _on_user_state(self, event: Any) -> None:
        data = _data(event)
        occurred = _occurred_at(_value(event, "created_at"))
        old_state = str(_value(event, "old_state", self._user_state))
        new_state = str(_value(event, "new_state", ""))
        if new_state == "speaking":
            if self._turn_id is not None and self._turn_has_assistant:
                self._finish_turn(occurred)
            self._ensure_turn(occurred)
            self._stt_started_at = occurred
            self._emit(
                "speech.started",
                occurred_at=occurred,
                status="unset",
                attributes={"speaker": "user", **data},
            )
            assert self._stt_span_id is not None
            if self._stt_span_id not in self._span_started:
                self._span_started.add(self._stt_span_id)
                self._emit(
                    "stt.started",
                    occurred_at=occurred,
                    status="unset",
                    span_id=self._stt_span_id,
                    attributes={"name": "speech recognition", "integration": "livekit"},
                )
            if self._agent_state == "speaking" and not self._playback_interrupted:
                self._playback_interrupted = True
                self._emit(
                    "voice.interruption",
                    occurred_at=occurred,
                    status="ok",
                    span_id=self._playback_span_id,
                    attributes={"evidence": "user_speech_during_agent_playback", **data},
                )
        elif old_state == "speaking" and new_state != "speaking":
            self._emit(
                "speech.stopped",
                occurred_at=occurred,
                status="ok",
                attributes={"speaker": "user", **data},
            )
        self._user_state = new_state or self._user_state

    def _on_agent_state(self, event: Any) -> None:
        data = _data(event)
        occurred = _occurred_at(_value(event, "created_at"))
        old_state = str(_value(event, "old_state", self._agent_state))
        new_state = str(_value(event, "new_state", ""))
        if new_state == "speaking" and old_state != "speaking":
            self._ensure_turn(occurred)
            current_speech = _value(self.agent_session, "current_speech")
            if current_speech is not None:
                self._active_speech = current_speech
            speech_id = _value(self._active_speech, "id")
            seed = speech_id or occurred.timestamp()
            self._playback_span_id = _external_id("spn", f"playback:{seed}")
            self._playback_started_at = occurred
            self._playback_interrupted = False
            self._emit(
                "playback.started",
                occurred_at=occurred,
                status="unset",
                span_id=self._playback_span_id,
                parent_span_id=self._tts_spans.get(str(speech_id)) if speech_id else None,
                attributes={"name": "audio playback", "speech_id": speech_id, **data},
            )
        elif old_state == "speaking" and new_state != "speaking":
            self._finish_playback(occurred)
        self._agent_state = new_state or self._agent_state

    def _finish_playback(self, occurred: datetime) -> None:
        if self._playback_span_id is None:
            return
        interrupted = self._playback_interrupted or bool(
            _value(self._active_speech, "interrupted", False)
        )
        duration_ms = None
        if self._playback_started_at is not None:
            duration_ms = max(0.0, (occurred - self._playback_started_at).total_seconds() * 1000)
        self._emit(
            "playback.interrupted" if interrupted else "playback.completed",
            occurred_at=occurred,
            status="cancelled" if interrupted else "ok",
            span_id=self._playback_span_id,
            attributes={"name": "audio playback", "interrupted": interrupted},
            duration_ms=duration_ms,
        )
        self._playback_span_id = None
        self._playback_started_at = None
        self._active_speech = None
        self._finish_turn(occurred, abandoned=interrupted and not self._turn_has_assistant)

    def _on_transcript(self, event: Any) -> None:
        transcript = _value(event, "transcript")
        if not isinstance(transcript, str) or not transcript:
            return
        occurred = _occurred_at(_value(event, "created_at"))
        self._ensure_turn(occurred)
        assert self._stt_span_id is not None
        if self._stt_span_id not in self._span_started:
            self._span_started.add(self._stt_span_id)
            self._stt_started_at = self._stt_started_at or occurred
            self._emit(
                "stt.started",
                occurred_at=occurred,
                status="unset",
                span_id=self._stt_span_id,
                attributes={"name": "speech recognition", "integration": "livekit"},
            )
        is_final = bool(_value(event, "is_final", True))
        attributes = {
            "name": "speech recognition",
            "transcript": transcript,
            "is_final": is_final,
            "livekit_item_id": _value(event, "item_id"),
            "speaker_id": _value(event, "speaker_id"),
            "language": _value(event, "language"),
        }
        self._emit(
            "stt.final" if is_final else "stt.interim",
            occurred_at=occurred,
            status="ok" if is_final else "unset",
            span_id=self._stt_span_id,
            attributes=attributes,
            output={"text": transcript} if is_final else None,
        )
        if is_final:
            # Speech-to-text latency is the gap between the user starting to
            # speak and the final transcript, not a provider-supplied constant.
            duration_ms = None
            if self._stt_started_at is not None:
                duration_ms = max(
                    0.0, (occurred - self._stt_started_at).total_seconds() * 1000
                )
            self._emit(
                "stt.completed",
                occurred_at=occurred,
                status="ok",
                span_id=self._stt_span_id,
                attributes=attributes,
                output={"text": transcript},
                duration_ms=duration_ms,
            )

    def _on_transcription_timeout(self, event: Any) -> None:
        occurred = _occurred_at(_value(event, "created_at"))
        self._ensure_turn(occurred)
        span_id = self._stt_span_id or _external_id("spn", "stt-timeout")
        self._emit(
            "stt.timeout",
            occurred_at=occurred,
            status="timeout",
            span_id=span_id,
            attributes={"name": "speech recognition", **_data(event)},
            error={
                "type": "TranscriptionTimeout",
                "code": "livekit_transcription_timeout",
                "message": "LiveKit did not produce a transcript for detected user speech",
                "retryable": True,
                "retry_count": 0,
            },
        )

    def _on_conversation_item(self, event: Any) -> None:
        item = _value(event, "item")
        item_type = str(_value(item, "type", ""))
        created_at = _value(event, "created_at", _value(item, "created_at"))
        occurred = _occurred_at(created_at)
        if item_type == "agent_handoff":
            old_agent = str(_value(item, "old_agent_id") or self.agent_name)
            new_agent = str(_value(item, "new_agent_id") or "unknown-agent")
            old_run_id = self._agent_run_id
            self._emit(
                "agent.completed",
                occurred_at=occurred,
                status="ok",
                agent_run_id=old_run_id,
                agent_name=old_agent,
                attributes={"semantic_agent": old_agent, "handoff": True},
            )
            self._emit(
                "agent.handoff",
                occurred_at=occurred,
                status="ok",
                agent_run_id=old_run_id,
                agent_name=old_agent,
                attributes={
                    "from_agent": old_agent,
                    "to_agent": new_agent,
                    "reason": "LiveKit AgentHandoff",
                    "outcome": None,
                },
            )
            self.agent_name = new_agent
            item_id = _value(item, "id")
            self._agent_run_id = _external_id("run", f"{item_id}:{new_agent}")
            self._emit(
                "agent.started",
                occurred_at=occurred,
                status="unset",
                agent_run_id=self._agent_run_id,
                parent_agent_run_id=old_run_id,
                agent_name=new_agent,
                attributes={"semantic_agent": new_agent, "livekit_item_id": item_id},
            )
            return
        role = str(_value(item, "role", ""))
        if role not in {"user", "assistant"}:
            return
        text = _value(item, "text_content") or _value(item, "raw_text_content")
        if callable(text):
            try:
                text = text()
            except Exception:
                text = None
        if text is None:
            content = _value(item, "content", [])
            if isinstance(content, list):
                text = "\n".join(part for part in content if isinstance(part, str)) or None
        attributes = {
            "role": role,
            "speaker": "user" if role == "user" else "agent",
            "transcript": text,
            "livekit_item_id": _value(item, "id"),
            "interrupted": bool(_value(item, "interrupted", False)),
        }
        if role == "user":
            turn_id = self._ensure_turn(occurred)
        else:
            # A LiveKit conversation item is a speaker utterance, while the
            # active pipeline turn represents the caller's request.  Reusing
            # that caller turn for an assistant message overwrites its speaker
            # and transcript in the dashboard. Materialize a small, separate
            # agent turn so transcript rows always retain their real speaker.
            item_id = _value(item, "id") or new_id("assistant-message")
            turn_id = _external_id("turn", f"assistant:{item_id}")
            self._emit(
                "turn.started",
                occurred_at=occurred,
                status="unset",
                turn_id=turn_id,
                attributes={"speaker": "agent", "integration": "livekit"},
            )
        self._emit(
            f"{role}.message",
            occurred_at=occurred,
            status="ok",
            turn_id=turn_id,
            attributes=attributes,
            input={"text": text} if role == "user" and text else None,
            output={"text": text} if role == "assistant" and text else None,
        )
        if role == "assistant":
            self._turn_has_assistant = True
            self._emit(
                "turn.completed",
                occurred_at=occurred,
                status="ok",
                turn_id=turn_id,
                attributes={"speaker": "agent", "integration": "livekit"},
            )

    def _on_speech_created(self, event: Any) -> None:
        occurred = _occurred_at(_value(event, "created_at"))
        self._ensure_turn(occurred)
        handle = _value(event, "speech_handle")
        self._active_speech = handle
        speech_id = str(_value(handle, "id") or new_id("speech"))
        span_id = _external_id("spn", f"tts:{speech_id}")
        self._tts_spans[speech_id] = span_id
        if span_id not in self._span_started:
            self._span_started.add(span_id)
            self._emit(
                "tts.started",
                occurred_at=occurred,
                status="unset",
                span_id=span_id,
                attributes={
                    "name": "speech synthesis",
                    "speech_id": speech_id,
                    "source": _value(event, "source"),
                    "user_initiated": bool(_value(event, "user_initiated", False)),
                },
            )

    def _metric_usage(
        self,
        data: dict[str, Any],
        provider: str | None,
        model: str | None,
    ) -> dict[str, Any] | None:
        usage = {
            "provider": provider,
            "model": model,
            "input_tokens": data.get("prompt_tokens", data.get("input_tokens")),
            "output_tokens": data.get("completion_tokens", data.get("output_tokens")),
            "cached_tokens": data.get("prompt_cached_tokens"),
            "total_tokens": data.get("total_tokens"),
            "audio_seconds": data.get("audio_duration"),
            "tts_characters": data.get("characters_count"),
        }
        compact = {key: value for key, value in usage.items() if value is not None}
        return compact or None

    def _on_metrics(self, event: Any) -> None:
        metric = _value(event, "metrics", event)
        data = _data(metric)
        metric_type = str(data.get("type") or type(metric).__name__).lower()
        if "llm" in metric_type or "realtime_model" in metric_type:
            stage = "llm"
        elif "stt" in metric_type:
            stage = "stt"
        elif "tts" in metric_type:
            stage = "tts"
        else:
            # VAD, turn-detector, and speaking-rate samples are high-frequency
            # internals, not customer-observable events. Exporting each sample
            # used to fill the queue before the terminal session event.
            return
        raw_metadata = data.get("metadata")
        metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
        provider = metadata.get("model_provider")
        model = metadata.get("model_name")
        request_id = data.get("request_id") or data.get("speech_id") or new_id("request")
        speech_id = data.get("speech_id")
        if stage == "tts" and speech_id and str(speech_id) in self._tts_spans:
            span_id = self._tts_spans[str(speech_id)]
        elif stage == "stt" and self._stt_span_id:
            span_id = self._stt_span_id
        else:
            span_id = _external_id("spn", f"{stage}:{request_id}")
        ended_at = _occurred_at(data.get("timestamp") or _value(event, "created_at"))
        duration_seconds = float(data.get("duration") or 0.0)
        started_at = ended_at - timedelta(seconds=max(0.0, duration_seconds))
        attributes = {
            "name": f"{stage} request",
            "livekit_request_id": request_id,
            "livekit_label": data.get("label"),
            "provider": provider,
            "model": model,
            "streamed": data.get("streamed"),
            "audio_duration_ms": (
                float(data["audio_duration"]) * 1000
                if data.get("audio_duration") is not None
                else None
            ),
        }
        first_byte = (
            data.get("ttft") if stage == "llm" else data.get("ttfb") if stage == "tts" else None
        )
        if isinstance(first_byte, (int, float)) and first_byte >= 0:
            attributes["ttft_ms" if stage == "llm" else "ttfb_ms"] = first_byte * 1000
        if span_id not in self._span_started:
            self._span_started.add(span_id)
            self._emit(
                f"{stage}.started",
                occurred_at=started_at,
                status="unset",
                span_id=span_id,
                provider=provider,
                attributes=attributes,
            )
        if isinstance(first_byte, (int, float)) and first_byte >= 0:
            self._emit(
                "llm.first_token" if stage == "llm" else "tts.first_audio",
                occurred_at=started_at + timedelta(seconds=first_byte),
                status="ok",
                span_id=span_id,
                provider=provider,
                attributes=attributes,
            )
        cancelled = bool(data.get("cancelled", False))
        measured_duration_ms = max(0.0, duration_seconds * 1000)
        self._emit(
            f"{stage}.cancelled" if cancelled else f"{stage}.completed",
            occurred_at=ended_at,
            status="cancelled" if cancelled else "ok",
            span_id=span_id,
            provider=provider,
            attributes=attributes,
            usage=self._metric_usage(data, provider, model),
            # A provider metric of 0 means "not measured"; emitting it would
            # overwrite a real speech-to-transcript duration on the same span.
            duration_ms=measured_duration_ms if measured_duration_ms > 0 else None,
        )

    def _on_session_usage(self, event: Any) -> None:
        usage = _data(_value(event, "usage", event))
        # LiveKit emits this whenever a live counter changes. The final state
        # is valuable; hundreds of intermediate duplicates are not.
        self._latest_session_usage = usage

    def _on_tool_update(self, event: Any) -> None:
        update = _value(event, "update", event)
        update_type = str(_value(update, "type", ""))
        occurred = _occurred_at(_value(event, "created_at"))
        if update_type == "tool_call_started":
            call = _value(update, "function_call")
            call_id = str(_value(call, "call_id") or _value(call, "id") or new_id("call"))
            name = str(_value(call, "name") or "tool")
            arguments = _json_arguments(_value(call, "arguments", {}))
            span_id = _external_id("spn", f"tool:{call_id}")
            self._tool_runs[call_id] = (span_id, occurred, name, arguments)
            self._span_started.add(span_id)
            self._emit(
                "tool.started",
                occurred_at=occurred,
                status="unset",
                span_id=span_id,
                attributes={
                    "name": name,
                    "protocol": "function",
                    "livekit_call_id": call_id,
                },
                input={"arguments": arguments},
            )
        elif update_type == "tool_call_ended":
            call_id = str(_value(update, "call_id") or _value(update, "id") or "")
            run = self._tool_runs.pop(call_id, None)
            if run is None:
                run = (
                    _external_id("spn", f"tool:{call_id}"),
                    occurred,
                    "tool",
                    {},
                )
            span_id, started, name, _arguments = run
            status = str(_value(update, "status", "done"))
            message = _value(update, "message")
            self._complete_tool(
                call_id,
                span_id=span_id,
                started=started,
                occurred=occurred,
                name=name,
                output=message,
                is_error=status == "error",
                cancelled=status == "cancelled",
            )
        elif update_type == "tool_call_updated":
            self._emit(
                "custom",
                occurred_at=occurred,
                status="ok",
                attributes={"custom_name": "livekit.tool_progress", **_data(update)},
            )

    def _complete_tool(
        self,
        call_id: str,
        *,
        span_id: str,
        started: datetime,
        occurred: datetime,
        name: str,
        output: Any,
        is_error: bool,
        cancelled: bool = False,
    ) -> None:
        self._completed_tools.add(call_id)
        status = "cancelled" if cancelled else "error" if is_error else "ok"
        suffix = status if status != "ok" else "completed"
        error = None
        if status != "ok":
            error = {
                "type": "LiveKitToolError" if is_error else "CancelledError",
                "code": "livekit_tool_error" if is_error else "cancelled",
                "message": str(
                    output
                    or ("Tool execution was cancelled" if cancelled else "Tool execution failed")
                ),
                "retryable": False,
                "retry_count": 0,
            }
        self._emit(
            f"tool.{suffix}",
            occurred_at=occurred,
            status=status,
            span_id=span_id,
            attributes={
                "name": name,
                "protocol": "function",
                "livekit_call_id": call_id,
            },
            output={"result": output} if output is not None and status == "ok" else None,
            error=error,
            duration_ms=max(0.0, (occurred - started).total_seconds() * 1000),
        )

    def _on_tools_executed(self, event: Any) -> None:
        calls = list(_value(event, "function_calls", []) or [])
        outputs = list(_value(event, "function_call_outputs", []) or [])
        occurred = _occurred_at(_value(event, "created_at"))
        for call, output in zip(calls, outputs, strict=False):
            call_id = str(_value(call, "call_id") or _value(call, "id") or new_id("call"))
            if call_id in self._completed_tools:
                continue
            name = str(_value(call, "name") or _value(output, "name") or "tool")
            run = self._tool_runs.pop(call_id, None)
            if run is None:
                span_id = _external_id("spn", f"tool:{call_id}")
                started = occurred
                arguments = _json_arguments(_value(call, "arguments", {}))
                self._emit(
                    "tool.started",
                    occurred_at=started,
                    status="unset",
                    span_id=span_id,
                    attributes={
                        "name": name,
                        "protocol": "function",
                        "livekit_call_id": call_id,
                    },
                    input={"arguments": arguments},
                )
            else:
                span_id, started, name, _arguments = run
            self._complete_tool(
                call_id,
                span_id=span_id,
                started=started,
                occurred=occurred,
                name=name,
                output=_value(output, "output"),
                is_error=bool(_value(output, "is_error", False)),
            )

    def _on_false_interruption(self, event: Any) -> None:
        self._emit(
            "custom",
            occurred_at=_occurred_at(_value(event, "created_at")),
            status="ok",
            attributes={"custom_name": "livekit.false_interruption", **_data(event)},
        )

    def _on_overlapping_speech(self, event: Any) -> None:
        data = _data(event)
        occurred = _occurred_at(_value(event, "detected_at", _value(event, "created_at")))
        if _value(event, "overlap_started_at") is not None:
            started = _occurred_at(_value(event, "overlap_started_at"))
            data["overlap_duration_ms"] = max(0.0, (occurred - started).total_seconds() * 1000)
        self._emit(
            "voice.talk_over",
            occurred_at=occurred,
            status="ok",
            span_id=self._playback_span_id,
            attributes={"evidence": "livekit.overlapping_speech", **data},
        )
        if bool(_value(event, "is_interruption", False)) and not self._playback_interrupted:
            self._playback_interrupted = True
            self._emit(
                "voice.interruption",
                occurred_at=occurred,
                status="ok",
                span_id=self._playback_span_id,
                attributes={"evidence": "livekit.overlapping_speech", **data},
            )

    def _on_error(self, event: Any) -> None:
        error = _value(event, "error", event)
        source = _value(event, "source")
        error_data = _data(error)
        source_data = _data(source)
        error_name = str(error_data.get("type") or type(error).__name__)
        combined = f"{error_name} {type(source).__name__}".lower()
        if "stt" in combined:
            stage = "stt"
        elif "tts" in combined:
            stage = "tts"
        elif "llm" in combined or "realtime" in combined:
            stage = "llm"
        else:
            stage = "livekit"
        provider = source_data.get("provider")
        message = error_data.get("message") or str(error)
        request_key = error_data.get("request_id") or new_id("error")
        self._emit(
            f"{stage}.error",
            occurred_at=_occurred_at(_value(event, "created_at")),
            status="error",
            span_id=_external_id("spn", f"{stage}:{request_key}"),
            provider=provider,
            attributes={"name": f"{stage} request", "model": source_data.get("model")},
            error={
                "type": error_name,
                "code": error_data.get("code"),
                "message": str(message),
                "retryable": bool(
                    error_data.get("recoverable", error_data.get("retryable", False))
                ),
                "retry_count": 0,
                "provider_request_id": error_data.get("request_id"),
            },
        )

    def _on_close(self, event: Any) -> None:
        self.close(event=event)

    def close(self, *, event: Any = None) -> None:
        """Detach listeners and finish the owned Voker session; safe to repeat."""

        if self._closed:
            return
        self._closed = True
        occurred = _occurred_at(_value(event, "created_at"))
        self._finish_playback(occurred)
        self._finish_turn(occurred, abandoned=not self._turn_has_assistant)
        close_error = _value(event, "error")
        close_reason = _value(event, "reason")
        if hasattr(close_reason, "value"):
            close_reason = close_reason.value
        if close_error is not None:
            status = "error"
        elif close_reason == "job_shutdown":
            status = "cancelled"
        else:
            status = "ok"
        error_payload = None
        if close_error is not None:
            error_payload = {
                "type": type(close_error).__name__,
                "message": str(close_error),
                "retryable": False,
                "retry_count": 0,
            }
        self._emit(
            "agent.error" if status == "error" else "agent.completed",
            occurred_at=occurred,
            status=status,
            error=error_payload,
            attributes={"semantic_agent": self.agent_name, "close_reason": close_reason},
        )
        if self._latest_session_usage is not None:
            self._emit(
                "custom",
                occurred_at=occurred,
                status="ok",
                attributes={
                    "custom_name": "livekit.session_usage",
                    "usage": self._latest_session_usage,
                    "final": True,
                },
            )
        if self.owns_session:
            if error_payload is not None:
                self._emit(
                    "session.error",
                    occurred_at=occurred,
                    status="error",
                    error=error_payload,
                    attributes={"close_reason": close_reason},
                )
            self._terminal_event = self._emit(
                "session.ended",
                occurred_at=occurred,
                status=status,
                error=error_payload,
                attributes={"close_reason": close_reason},
            )
        off = _value(self.agent_session, "off")
        if callable(off):
            for name, callback in self._listeners:
                try:
                    off(name, callback)
                except Exception:
                    pass
        self._listeners.clear()


def observe(
    agent_session: Any,
    session: VoiceSession | None = None,
    *,
    context: Any = None,
    agent: str = "livekit-agent",
    version: str | None = None,
    client: VokerVoice | None = None,
    session_id: str | None = None,
    trace_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    recording: dict[str, Any] | None = None,
) -> LiveKitObserver:
    """Observe a LiveKit session with one call.

    Passing an existing :class:`VoiceSession` remains supported. Otherwise the
    observer creates and completes a session using environment configuration or
    the supplied ``client``.
    """

    inferred_session_id, context_data = _context_metadata(context)
    combined_metadata = {**context_data, **(metadata or {})}
    if recording is not None:
        combined_metadata["recording"] = recording
    owns_session = session is None
    owns_client = session is None and client is None
    if session is None:
        voice_client = client or VokerVoice()
        session = voice_client.session(
            agent=agent,
            session_id=session_id or inferred_session_id,
            trace_id=trace_id,
            version=version,
            metadata=combined_metadata,
        )
    observer = LiveKitObserver(
        agent_session,
        session,
        owns_session=owns_session,
        owns_client=owns_client,
        agent=agent if owns_session else session.root_agent,
        version=version if owns_session else session.version,
    )
    add_shutdown_callback = _value(context, "add_shutdown_callback")
    if owns_session and callable(add_shutdown_callback):

        async def drain_voker_telemetry(_: str = "") -> None:
            # LiveKit runs shutdown callbacks after the voice pipeline is
            # finalized. Draining here preserves the terminal event without
            # blocking real-time audio or the AgentSession close handler.
            # Keep this bounded below LiveKit's child-process shutdown window.
            # The close callback runs on LiveKit's audio/session loop, so it
            # only records the terminal event. Deliver its idempotent copy in
            # this post-session hook, off the event loop and with a deadline.
            if observer._terminal_event is not None:
                await asyncio.to_thread(
                    observer.session.client.deliver_terminal_event,
                    observer._terminal_event,
                    timeout_seconds=4.0,
                )
            await observer.session.client.aflush(timeout=4.0)
            if observer.owns_client:
                await observer.session.client.aclose()

        add_shutdown_callback(drain_voker_telemetry)
    return observer
