import contextvars
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from voker_voice.redaction import redact

if TYPE_CHECKING:
    from voker_voice.client import VokerVoice

_active_session: contextvars.ContextVar["VoiceSession | None"] = contextvars.ContextVar(
    "voker_voice_active_session", default=None
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
        metadata: dict[str, Any] | None,
    ) -> None:
        self.client = client
        self.agent = agent
        self.session_id = session_id or new_id("ses")
        self.trace_id = trace_id or new_id("trc")
        self.metadata = redact(metadata or {})
        self._token: contextvars.Token[VoiceSession | None] | None = None
        self._sequence = 0

    def __enter__(self) -> "VoiceSession":
        self._token = _active_session.set(self)
        self.emit("session.started", status="ok", attributes=self.metadata)
        return self

    def __exit__(self, exc_type: object, exc: BaseException | None, traceback: object) -> bool:
        if exc is None:
            self.emit("session.ended", status="ok")
        else:
            self.emit("session.error", status="error", error=self._error_payload(exc))
            self.emit("session.ended", status="error", error=self._error_payload(exc))
        if self._token is not None:
            _active_session.reset(self._token)
        self.client.flush()
        return False

    async def __aenter__(self) -> "VoiceSession":
        return self.__enter__()

    async def __aexit__(
        self, exc_type: object, exc: BaseException | None, traceback: object
    ) -> bool:
        return self.__exit__(exc_type, exc, traceback)

    def emit(
        self,
        event_type: str,
        *,
        status: str = "unset",
        attributes: dict[str, Any] | None = None,
        input: dict[str, Any] | None = None,
        output: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        usage: dict[str, Any] | None = None,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        turn_id: str | None = None,
        agent_run_id: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        self._sequence += 1
        event: dict[str, Any] = {
            "schema_version": "1.0",
            "event_id": new_id("evt"),
            "event_type": event_type,
            "occurred_at": datetime.now(UTC).isoformat(),
            "sequence": self._sequence,
            "external_session_id": self.session_id,
            "trace_id": self.trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "turn_id": turn_id,
            "agent_run_id": agent_run_id,
            "agent": {"name": self.agent},
            "source": {"sdk": "voker-voice-python", "sdk_version": self.client.version},
            "status": status,
            "attributes": redact(attributes or {}),
        }
        if input is not None and self.client.capture_inputs:
            event["input"] = redact(input)
        if output is not None and self.client.capture_outputs:
            event["output"] = redact(output)
        if error is not None:
            event["error"] = redact(error)
        if usage is not None:
            event["usage"] = redact(usage)
        if duration_ms is not None:
            event["duration_ms"] = duration_ms
        self.client._emit(event)

    def span(
        self,
        kind: str,
        *,
        name: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> "SpanContext":
        merged = {"name": name or kind, **(attributes or {})}
        if provider:
            merged["provider"] = provider
        if model:
            merged["model"] = model
        return SpanContext(self, kind=kind, parent_span_id=parent_span_id, attributes=merged)

    def tool(
        self,
        name: str,
        *,
        protocol: str = "function",
        server: str | None = None,
        arguments: dict[str, Any] | None = None,
    ) -> "SpanContext":
        attributes = {"name": name, "protocol": protocol, "arguments": arguments or {}}
        if server:
            attributes["server"] = server
        return SpanContext(self, kind="tool", attributes=attributes)

    @contextmanager
    def agent_scope(self, name: str) -> Generator["SpanContext", None, None]:
        with self.span("agent", name=name, attributes={"semantic_agent": name}) as span:
            yield span

    def handoff(self, *, from_agent: str, to_agent: str, reason: str | None = None) -> None:
        self.emit(
            "agent.handoff",
            status="ok",
            attributes={"from_agent": from_agent, "to_agent": to_agent, "reason": reason},
        )

    @staticmethod
    def _error_payload(error: BaseException) -> dict[str, Any]:
        return {
            "type": type(error).__name__,
            "message": str(error),
            "retryable": False,
            "retry_count": 0,
        }


class SpanContext:
    def __init__(
        self,
        session: VoiceSession,
        *,
        kind: str,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        self.session = session
        self.kind = kind
        self.span_id = new_id("spn")
        self.parent_span_id = parent_span_id
        self.attributes = attributes or {}
        self.output: dict[str, Any] | None = None
        self.usage: dict[str, Any] | None = None
        self._started_at: datetime | None = None

    def __enter__(self) -> "SpanContext":
        self._started_at = datetime.now(UTC)
        self.session.emit(
            f"{self.kind}.started",
            status="unset",
            span_id=self.span_id,
            parent_span_id=self.parent_span_id,
            attributes=self.attributes,
        )
        return self

    def __exit__(self, exc_type: object, exc: BaseException | None, traceback: object) -> bool:
        started_at = self._started_at or datetime.now(UTC)
        duration_ms = (datetime.now(UTC) - started_at).total_seconds() * 1000
        if exc is None:
            self.session.emit(
                f"{self.kind}.completed",
                status="ok",
                span_id=self.span_id,
                parent_span_id=self.parent_span_id,
                attributes=self.attributes,
                output=self.output,
                usage=self.usage,
                duration_ms=duration_ms,
            )
        else:
            self.session.emit(
                f"{self.kind}.error",
                status="error",
                span_id=self.span_id,
                parent_span_id=self.parent_span_id,
                attributes=self.attributes,
                error=self.session._error_payload(exc),
                duration_ms=duration_ms,
            )
        return False

    async def __aenter__(self) -> "SpanContext":
        return self.__enter__()

    async def __aexit__(
        self, exc_type: object, exc: BaseException | None, traceback: object
    ) -> bool:
        return self.__exit__(exc_type, exc, traceback)

    def set_output(self, output: dict[str, Any]) -> None:
        self.output = output

    def set_usage(self, **usage: Any) -> None:
        self.usage = usage


def current_session() -> VoiceSession | None:
    return _active_session.get()
