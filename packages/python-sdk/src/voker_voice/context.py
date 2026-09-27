import asyncio
import contextvars
import traceback as traceback_module
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from voker_voice.client import VokerVoice

_active_session: contextvars.ContextVar["VoiceSession | None"] = contextvars.ContextVar(
    "voker_voice_active_session", default=None
)
_active_span_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "voker_voice_active_span_id", default=None
)
_active_turn_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "voker_voice_active_turn_id", default=None
)
_active_agent_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "voker_voice_active_agent_run_id", default=None
)
_active_agent_name: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "voker_voice_active_agent_name", default=None
)
_active_agent_version: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "voker_voice_active_agent_version", default=None
)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class VoiceSession:
    def __init__(
        self,
        client: "VokerVoice",
        *,
        agent: str,
        session_id: str | None,
        trace_id: str | None,
        version: str | None,
        metadata: dict[str, Any] | None,
    ) -> None:
        self.client = client
        self.root_agent = agent
        self.session_id = session_id or new_id("ses")
        self.trace_id = trace_id or new_id("trc")
        self.version = version
        self.metadata = self.client._sanitize(metadata or {})
        self._token: contextvars.Token[VoiceSession | None] | None = None
        self._sequence = 0

    def completion_manifest(self) -> dict[str, int]:
        terminal_sequence = self._sequence + 1
        return {
            "expected_last_sequence": terminal_sequence,
            "generated_event_count": terminal_sequence,
        }

    def __enter__(self) -> "VoiceSession":
        self._token = _active_session.set(self)
        self.emit("session.started", status="ok", attributes=self.metadata)
        return self

    def _finish(self, exc: BaseException | None) -> None:
        status = status_for_exception(exc)
        if exc is not None:
            self.emit("session.error", status=status, error=self._error_payload(exc))
        self.emit(
            "session.ended",
            status=status,
            error=self._error_payload(exc) if exc else None,
            attributes=self.completion_manifest(),
        )
        if self._token is not None:
            _active_session.reset(self._token)
            self._token = None

    def __exit__(
        self, exc_type: object, exc: BaseException | None, traceback: object
    ) -> Literal[False]:
        self._finish(exc)
        self.client.flush(timeout=self.client.session_flush_timeout)
        return False

    async def __aenter__(self) -> "VoiceSession":
        return self.__enter__()

    async def __aexit__(
        self, exc_type: object, exc: BaseException | None, traceback: object
    ) -> Literal[False]:
        self._finish(exc)
        await self.client.aflush(timeout=self.client.session_flush_timeout)
        return False

    def emit(
        self,
        event_type: str,
        *,
        occurred_at: datetime | str | None = None,
        status: str = "unset",
        source: dict[str, Any] | None = None,
        attributes: dict[str, Any] | None = None,
        input: dict[str, Any] | None = None,
        output: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        usage: dict[str, Any] | None = None,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        turn_id: str | None = None,
        agent_run_id: str | None = None,
        parent_agent_run_id: str | None = None,
        agent_name: str | None = None,
        agent_version: str | None = None,
        duration_ms: float | None = None,
    ) -> dict[str, Any]:
        self._sequence += 1
        effective_agent = agent_name or _active_agent_name.get() or self.root_agent
        effective_version = agent_version or _active_agent_version.get() or self.version
        captured_attributes = dict(attributes or {})
        if not self.client.capture_transcripts and "transcript" in captured_attributes:
            captured_attributes.pop("transcript")
            captured_attributes["transcript_omitted"] = True
        if not self.client.capture_audio_metadata:
            audio_keys = [
                key
                for key in captured_attributes
                if key.startswith("audio") or key.startswith("recording")
            ]
            for key in audio_keys:
                captured_attributes.pop(key)
            if audio_keys:
                captured_attributes["audio_metadata_omitted"] = True
        emitted_at = occurred_at or datetime.now(UTC)
        event: dict[str, Any] = {
            "schema_version": "1.0",
            "event_id": new_id("evt"),
            "event_type": event_type,
            "occurred_at": (
                emitted_at.isoformat() if isinstance(emitted_at, datetime) else emitted_at
            ),
            "sequence": self._sequence,
            "external_session_id": self.session_id,
            "trace_id": self.trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "turn_id": turn_id or _active_turn_id.get(),
            "agent_run_id": agent_run_id or _active_agent_run_id.get(),
            "parent_agent_run_id": parent_agent_run_id,
            "agent": {"name": effective_agent, "version": effective_version},
            "source": {
                "sdk": "voker-voice-python",
                "sdk_version": self.client.version,
                **(source or {}),
            },
            "status": status,
            "attributes": self.client._sanitize(captured_attributes),
        }
        if input is not None and self.client.capture_inputs:
            event["input"] = self.client._sanitize(input)
        if output is not None and self.client.capture_outputs:
            event["output"] = self.client._sanitize(output)
        if error is not None:
            event["error"] = self.client._sanitize(error)
        if usage is not None:
            event["usage"] = self.client._sanitize(usage)
        if duration_ms is not None:
            event["duration_ms"] = duration_ms
        return self.client._emit(event)

    def span(
        self,
        kind: str,
        *,
        name: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
        input: dict[str, Any] | None = None,
    ) -> "SpanContext":
        merged = {"name": name or kind, **(attributes or {})}
        if provider:
            merged["provider"] = provider
        if model:
            merged["model"] = model
        return SpanContext(
            self,
            kind=kind,
            parent_span_id=parent_span_id,
            attributes=merged,
            input=input,
        )

    def tool(
        self,
        name: str,
        *,
        protocol: str = "function",
        server: str | None = None,
        arguments: dict[str, Any] | None = None,
        retry_count: int = 0,
    ) -> "SpanContext":
        attributes = {"name": name, "protocol": protocol, "retry_count": retry_count}
        if server:
            attributes["server"] = server
        tool_input = {"arguments": arguments or {}} if self.client.capture_tool_data else None
        return SpanContext(self, kind="tool", attributes=attributes, input=tool_input)

    def turn(
        self,
        *,
        speaker: str,
        turn_id: str | None = None,
        transcript: str | None = None,
    ) -> "TurnContext":
        return TurnContext(self, speaker=speaker, turn_id=turn_id, transcript=transcript)

    def agent(
        self,
        name: str,
        *,
        version: str | None = None,
        run_id: str | None = None,
    ) -> "AgentContext":
        return AgentContext(self, name=name, version=version, run_id=run_id)

    def agent_scope(self, name: str) -> "AgentContext":
        """Backward-compatible alias for the documented agent scope."""

        return self.agent(name)

    def handoff(
        self,
        *,
        from_agent: str,
        to_agent: str,
        reason: str | None = None,
        outcome: str | None = None,
    ) -> None:
        self.emit(
            "agent.handoff",
            status="ok",
            attributes={
                "from_agent": from_agent,
                "to_agent": to_agent,
                "reason": reason,
                "outcome": outcome,
            },
        )

    def record_outcome(self, outcome: str, *, source: str = "explicit") -> None:
        self.emit(
            "outcome.recorded",
            status="ok",
            attributes={"outcome": outcome, "source": source},
        )

    def custom(
        self,
        name: str,
        *,
        attributes: dict[str, Any] | None = None,
        status: str = "ok",
    ) -> None:
        """Emit a namespaced extension event without expanding the canonical vocabulary."""

        if "." not in name:
            raise ValueError("custom event names must be namespaced, for example 'acme.routing'")
        self.emit(
            "custom",
            status=status,
            attributes={"custom_name": name, **(attributes or {})},
        )

    def activate(
        self,
        *,
        span_id: str | None = None,
        turn_id: str | None = None,
        agent_run_id: str | None = None,
        agent_name: str | None = None,
        agent_version: str | None = None,
    ) -> "TraceBinding":
        """Bind this trace to nested framework work without emitting lifecycle events."""

        return TraceBinding(
            self,
            span_id=span_id,
            turn_id=turn_id,
            agent_run_id=agent_run_id,
            agent_name=agent_name,
            agent_version=agent_version,
        )

    def _error_payload(self, error: BaseException) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": type(error).__name__,
            "message": str(error),
            "retryable": False,
            "retry_count": 0,
        }
        if self.client.capture_stacktraces:
            payload["stacktrace"] = "".join(
                traceback_module.format_exception(type(error), error, error.__traceback__)
            )
        return payload


def status_for_exception(error: BaseException | None) -> str:
    if error is None:
        return "ok"
    if isinstance(error, asyncio.CancelledError):
        return "cancelled"
    if isinstance(error, TimeoutError):
        return "timeout"
    return "error"


class TraceBinding:
    """Temporarily propagate an existing canonical trace into framework callbacks/tasks."""

    def __init__(
        self,
        session: VoiceSession,
        *,
        span_id: str | None,
        turn_id: str | None,
        agent_run_id: str | None,
        agent_name: str | None,
        agent_version: str | None,
    ) -> None:
        self.session = session
        self.values = (span_id, turn_id, agent_run_id, agent_name, agent_version)
        self.tokens: list[tuple[contextvars.ContextVar[Any], contextvars.Token[Any]]] = []

    def __enter__(self) -> "TraceBinding":
        bindings: tuple[tuple[contextvars.ContextVar[Any], Any], ...] = (
            (_active_session, self.session),
            (_active_span_id, self.values[0]),
            (_active_turn_id, self.values[1]),
            (_active_agent_run_id, self.values[2]),
            (_active_agent_name, self.values[3]),
            (_active_agent_version, self.values[4]),
        )
        self.tokens = [(variable, variable.set(value)) for variable, value in bindings]
        return self

    def __exit__(
        self, exc_type: object, exc: BaseException | None, traceback: object
    ) -> Literal[False]:
        for variable, token in reversed(self.tokens):
            variable.reset(token)
        self.tokens.clear()
        return False

    async def __aenter__(self) -> "TraceBinding":
        return self.__enter__()

    async def __aexit__(
        self, exc_type: object, exc: BaseException | None, traceback: object
    ) -> Literal[False]:
        return self.__exit__(exc_type, exc, traceback)


class TurnContext:
    def __init__(
        self,
        session: VoiceSession,
        *,
        speaker: str,
        turn_id: str | None,
        transcript: str | None,
    ) -> None:
        self.session = session
        self.speaker = speaker
        self.turn_id = turn_id or new_id("turn")
        self.transcript = transcript
        self._token: contextvars.Token[str | None] | None = None

    def __enter__(self) -> "TurnContext":
        self._token = _active_turn_id.set(self.turn_id)
        attributes: dict[str, Any] = {"speaker": self.speaker}
        if self.transcript is not None and self.session.client.capture_transcripts:
            attributes["transcript"] = self.transcript
        elif self.transcript is not None:
            attributes["transcript_omitted"] = True
        self.session.emit(
            "turn.started",
            status="unset",
            turn_id=self.turn_id,
            attributes=attributes,
        )
        return self

    def set_transcript(self, transcript: str) -> None:
        self.transcript = transcript

    def __exit__(
        self, exc_type: object, exc: BaseException | None, traceback: object
    ) -> Literal[False]:
        status = status_for_exception(exc)
        attributes: dict[str, Any] = {"speaker": self.speaker}
        if self.transcript is not None and self.session.client.capture_transcripts:
            attributes["transcript"] = self.transcript
        elif self.transcript is not None:
            attributes["transcript_omitted"] = True
        event_type = "turn.completed" if exc is None else "turn.abandoned"
        self.session.emit(
            event_type,
            status=status,
            turn_id=self.turn_id,
            attributes=attributes,
            error=self.session._error_payload(exc) if exc else None,
        )
        if self._token is not None:
            _active_turn_id.reset(self._token)
        return False

    async def __aenter__(self) -> "TurnContext":
        return self.__enter__()

    async def __aexit__(
        self, exc_type: object, exc: BaseException | None, traceback: object
    ) -> Literal[False]:
        return self.__exit__(exc_type, exc, traceback)


class AgentContext:
    def __init__(
        self,
        session: VoiceSession,
        *,
        name: str,
        version: str | None,
        run_id: str | None,
    ) -> None:
        self.session = session
        self.name = name
        self.version = version
        self.run_id = run_id or new_id("run")
        self.parent_run_id = _active_agent_run_id.get()
        self._run_token: contextvars.Token[str | None] | None = None
        self._name_token: contextvars.Token[str | None] | None = None
        self._version_token: contextvars.Token[str | None] | None = None

    def __enter__(self) -> "AgentContext":
        self._run_token = _active_agent_run_id.set(self.run_id)
        self._name_token = _active_agent_name.set(self.name)
        self._version_token = _active_agent_version.set(self.version or self.session.version)
        self.session.emit(
            "agent.started",
            status="unset",
            agent_run_id=self.run_id,
            parent_agent_run_id=self.parent_run_id,
            agent_name=self.name,
            agent_version=self.version,
            attributes={"semantic_agent": self.name},
        )
        return self

    def __exit__(
        self, exc_type: object, exc: BaseException | None, traceback: object
    ) -> Literal[False]:
        status = status_for_exception(exc)
        self.session.emit(
            "agent.completed" if exc is None else "agent.error",
            status=status,
            agent_run_id=self.run_id,
            parent_agent_run_id=self.parent_run_id,
            agent_name=self.name,
            agent_version=self.version,
            attributes={"semantic_agent": self.name},
            error=self.session._error_payload(exc) if exc else None,
        )
        if self._version_token is not None:
            _active_agent_version.reset(self._version_token)
        if self._name_token is not None:
            _active_agent_name.reset(self._name_token)
        if self._run_token is not None:
            _active_agent_run_id.reset(self._run_token)
        return False

    async def __aenter__(self) -> "AgentContext":
        return self.__enter__()

    async def __aexit__(
        self, exc_type: object, exc: BaseException | None, traceback: object
    ) -> Literal[False]:
        return self.__exit__(exc_type, exc, traceback)


class SpanContext:
    def __init__(
        self,
        session: VoiceSession,
        *,
        kind: str,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
        input: dict[str, Any] | None = None,
    ) -> None:
        self.session = session
        self.kind = kind
        self.span_id = new_id("spn")
        self.parent_span_id = parent_span_id or _active_span_id.get()
        self.attributes = attributes or {}
        self.input = input
        self.output: dict[str, Any] | None = None
        self.usage: dict[str, Any] | None = None
        self.error: dict[str, Any] | None = None
        self._forced_status: str | None = None
        self._started_at: datetime | None = None
        self._token: contextvars.Token[str | None] | None = None

    def __enter__(self) -> "SpanContext":
        self._started_at = datetime.now(UTC)
        self._token = _active_span_id.set(self.span_id)
        self.session.emit(
            f"{self.kind}.started",
            status="unset",
            span_id=self.span_id,
            parent_span_id=self.parent_span_id,
            attributes=self.attributes,
            input=self.input,
        )
        return self

    def __exit__(
        self, exc_type: object, exc: BaseException | None, traceback: object
    ) -> Literal[False]:
        started_at = self._started_at or datetime.now(UTC)
        duration_ms = (datetime.now(UTC) - started_at).total_seconds() * 1000
        protocol_error = self._protocol_error()
        status = status_for_exception(exc) if exc is not None else self._forced_status or "ok"
        error = self.session._error_payload(exc) if exc else self.error or protocol_error
        if error is not None and status == "ok":
            status = "error"
        suffix = "completed" if status == "ok" else status
        output = self.output
        attributes = dict(self.attributes)
        if self.kind == "tool" and not self.session.client.capture_tool_data:
            output = None
            attributes["tool_data_omitted"] = True
        self.session.emit(
            f"{self.kind}.{suffix}",
            status=status,
            span_id=self.span_id,
            parent_span_id=self.parent_span_id,
            attributes=attributes,
            output=output,
            error=error,
            usage=self.usage,
            duration_ms=duration_ms,
        )
        if self._token is not None:
            _active_span_id.reset(self._token)
        return False

    async def __aenter__(self) -> "SpanContext":
        return self.__enter__()

    async def __aexit__(
        self, exc_type: object, exc: BaseException | None, traceback: object
    ) -> Literal[False]:
        return self.__exit__(exc_type, exc, traceback)

    def set_output(self, output: dict[str, Any]) -> None:
        self.output = output

    def set_input(self, input: dict[str, Any]) -> None:
        self.input = input

    def set_usage(self, **usage: Any) -> None:
        self.usage = usage

    def set_error(
        self,
        message: str,
        *,
        error_type: str = "ToolError",
        code: str | None = None,
        retryable: bool = False,
        retry_count: int = 0,
    ) -> None:
        self.error = {
            "type": error_type,
            "code": code,
            "message": message,
            "retryable": retryable,
            "retry_count": retry_count,
        }

    def set_timeout(self, message: str = "Operation timed out") -> None:
        self._forced_status = "timeout"
        self.set_error(message, error_type="TimeoutError", code="timeout", retryable=True)

    def set_cancelled(self, message: str = "Operation was cancelled") -> None:
        self._forced_status = "cancelled"
        self.set_error(message, error_type="CancelledError", code="cancelled")

    def _protocol_error(self) -> dict[str, Any] | None:
        if self.kind != "tool" or self.attributes.get("protocol") != "mcp":
            return None
        if not isinstance(self.output, dict):
            return None
        is_error = self.output.get("isError", self.output.get("is_error", False))
        if is_error is not True:
            return None
        message = self.output.get("message") or self.output.get("content") or "MCP tool failed"
        return {
            "type": "MCPToolError",
            "code": "mcp_tool_error",
            "message": str(message),
            "retryable": False,
            "retry_count": int(self.attributes.get("retry_count", 0)),
        }


def current_session() -> VoiceSession | None:
    return _active_session.get()


def current_span_id() -> str | None:
    return _active_span_id.get()


def current_turn_id() -> str | None:
    return _active_turn_id.get()


def current_agent_run_id() -> str | None:
    return _active_agent_run_id.get()
