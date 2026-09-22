"""LangGraph integration built on public LangChain and LangGraph callbacks."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from threading import RLock
from typing import Any

try:
    from langgraph.callbacks import GraphCallbackHandler as _GraphCallbackHandler
except ImportError:  # pragma: no cover - optional dependency guard
    try:
        from langchain_core.callbacks import (  # type: ignore[assignment]
            BaseCallbackHandler as _GraphCallbackHandler,
        )
    except ImportError:

        class _GraphCallbackHandler:  # type: ignore[no-redef]
            """Fallback that keeps the core SDK importable without optional packages."""


try:
    from langgraph.errors import GraphInterrupt, GraphRecursionError, InvalidUpdateError
    from langgraph.types import Command

    _LANGGRAPH_TYPES_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency guard
    _LANGGRAPH_TYPES_AVAILABLE = False

    class GraphInterrupt(Exception):  # type: ignore[no-redef]
        pass

    class GraphRecursionError(Exception):  # type: ignore[no-redef]
        pass

    class InvalidUpdateError(Exception):  # type: ignore[no-redef]
        pass

    class Command:  # type: ignore[no-redef]
        resume: Any = None


from voker_voice.client import VokerVoice
from voker_voice.context import (
    VoiceSession,
    current_agent_run_id,
    current_session,
    current_span_id,
    current_turn_id,
    new_id,
    status_for_exception,
)


def _value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {"value": dumped}
    if hasattr(value, "__dict__"):
        return {key: item for key, item in vars(value).items() if not key.startswith("_")}
    return {"value": value}


def _name(serialized: dict[str, Any] | None, fallback: str) -> str:
    descriptor = serialized or {}
    identifier = descriptor.get("id")
    if isinstance(identifier, list) and identifier:
        identifier = identifier[-1]
    return str(descriptor.get("name") or identifier or fallback)


def _error_category(error: BaseException) -> str:
    if _LANGGRAPH_TYPES_AVAILABLE and isinstance(error, GraphRecursionError):
        return "recursion_limit"
    if _LANGGRAPH_TYPES_AVAILABLE and isinstance(error, InvalidUpdateError):
        message = str(error).lower()
        if "concurrent" in message:
            return "invalid_concurrent_update"
        if "node" in message and "return" in message:
            return "invalid_node_return"
        return "invalid_state_update"
    if isinstance(error, asyncio.CancelledError):
        return "cancelled"
    if isinstance(error, TimeoutError):
        return "timeout"
    return "execution_error"


def _is_graph_interrupt(error: BaseException) -> bool:
    return _LANGGRAPH_TYPES_AVAILABLE and isinstance(error, GraphInterrupt)


def _resume_value(value: Any) -> Any:
    if _LANGGRAPH_TYPES_AVAILABLE and isinstance(value, Command):
        return value.resume
    return None


def _interrupts_from_result(value: Any) -> list[Any]:
    if isinstance(value, dict):
        interrupts = value.get("__interrupt__")
        if isinstance(interrupts, (list, tuple)):
            return list(interrupts)
    interrupts = getattr(value, "__interrupt__", None)
    return list(interrupts) if isinstance(interrupts, (list, tuple)) else []


@dataclass
class _Run:
    span_id: str
    parent_span_id: str | None
    started: float
    name: str
    kind: str
    attributes: dict[str, Any]


class VokerLangGraphCallback(_GraphCallbackHandler):
    """Translate framework nodes, models, tools, retries, and lifecycle events."""

    def __init__(
        self,
        session: VoiceSession,
        *,
        graph_span_id: str | None = None,
        turn_id: str | None = None,
        agent_run_id: str | None = None,
        agent_name: str | None = None,
        agent_version: str | None = None,
    ) -> None:
        super().__init__()
        self.session = session
        self.graph_span_id = graph_span_id
        self.turn_id = turn_id
        self.agent_run_id = agent_run_id
        self.agent_name = agent_name or session.root_agent
        self.agent_version = agent_version or session.version
        self._runs: dict[uuid.UUID, _Run] = {}
        self._parents: dict[uuid.UUID, uuid.UUID | None] = {}
        self._lock = RLock()
        self.interrupted = False
        self.resumed = False

    def _emit(self, event_type: str, **kwargs: Any) -> None:
        self.session.emit(
            event_type,
            source={"integration": "langgraph"},
            turn_id=kwargs.pop("turn_id", self.turn_id),
            agent_run_id=kwargs.pop("agent_run_id", self.agent_run_id),
            agent_name=kwargs.pop("agent_name", self.agent_name),
            agent_version=kwargs.pop("agent_version", self.agent_version),
            **kwargs,
        )

    def _remember_parent(self, run_id: uuid.UUID, parent_run_id: uuid.UUID | None) -> None:
        with self._lock:
            self._parents[run_id] = parent_run_id

    def _parent_span(self, run_id: uuid.UUID | None) -> str | None:
        with self._lock:
            visited: set[uuid.UUID] = set()
            current = run_id
            while current is not None and current not in visited:
                visited.add(current)
                run = self._runs.get(current)
                if run is not None:
                    return run.span_id
                current = self._parents.get(current)
        return self.graph_span_id

    def _start(
        self,
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None,
        kind: str,
        name: str,
        attributes: dict[str, Any],
        input: dict[str, Any] | None,
    ) -> None:
        self._remember_parent(run_id, parent_run_id)
        span_id = f"lg_{run_id.hex}"
        run = _Run(
            span_id=span_id,
            parent_span_id=self._parent_span(parent_run_id),
            started=time.monotonic(),
            name=name,
            kind=kind,
            attributes=attributes,
        )
        with self._lock:
            self._runs[run_id] = run
        self._emit(
            f"{kind}.started",
            status="unset",
            span_id=run.span_id,
            parent_span_id=run.parent_span_id,
            attributes=attributes,
            input=input,
        )

    def _finish(
        self,
        *,
        run_id: uuid.UUID,
        output: dict[str, Any] | None = None,
        error: BaseException | None = None,
        usage: dict[str, Any] | None = None,
        status_override: str | None = None,
    ) -> None:
        with self._lock:
            run = self._runs.pop(run_id, None)
        if run is None:
            return
        status = status_override or status_for_exception(error)
        suffix = "completed" if status == "ok" else status
        attributes = dict(run.attributes)
        if error is not None and status_override is None:
            attributes["error_category"] = _error_category(error)
        self._emit(
            f"{run.kind}.{suffix}",
            status=status,
            span_id=run.span_id,
            parent_span_id=run.parent_span_id,
            attributes=attributes,
            output=output,
            usage=usage,
            error=(
                self.session._error_payload(error)
                if error is not None and status_override is None
                else None
            ),
            duration_ms=(time.monotonic() - run.started) * 1000,
        )

    def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any],
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        name: str | None = None,
        **_: Any,
    ) -> None:
        self._remember_parent(run_id, parent_run_id)
        metadata = metadata or {}
        tags = tags or []
        node_name = metadata.get("langgraph_node")
        is_node = isinstance(node_name, str) and any(tag.startswith("graph:step:") for tag in tags)
        if not is_node:
            return
        display_name = str(node_name or name or _name(serialized, "node"))
        self._start(
            run_id=run_id,
            parent_run_id=parent_run_id,
            kind="graph.node",
            name=display_name,
            attributes={
                "name": display_name,
                "framework": "langgraph",
                "run_id": str(run_id),
                "step": metadata.get("langgraph_step"),
                "triggers": metadata.get("langgraph_triggers"),
                "checkpoint_namespace": metadata.get("langgraph_checkpoint_ns"),
                "semantic_agent": False,
            },
            input=inputs,
        )

    def on_chain_end(self, outputs: dict[str, Any], *, run_id: uuid.UUID, **_: Any) -> None:
        self._finish(run_id=run_id, output=_payload(outputs))

    def on_chain_error(self, error: BaseException, *, run_id: uuid.UUID, **_: Any) -> None:
        if _is_graph_interrupt(error):
            self._record_interrupts(list(error.args[0]) if error.args else [])
            self._finish(run_id=run_id, error=error, status_override="cancelled")
            return
        self._finish(run_id=run_id, error=error)

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
        invocation_params: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        params = invocation_params or {}
        model = params.get("model") or params.get("model_name")
        provider = (metadata or {}).get("ls_provider")
        name = _name(serialized, str(model or "language model"))
        self._start(
            run_id=run_id,
            parent_run_id=parent_run_id,
            kind="llm",
            name=name,
            attributes={
                "name": name,
                "framework": "langgraph",
                "run_id": str(run_id),
                "provider": provider,
                "model": model,
            },
            input={"prompts": prompts},
        )

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
        invocation_params: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        params = invocation_params or {}
        model = params.get("model") or params.get("model_name")
        provider = (metadata or {}).get("ls_provider")
        name = _name(serialized, str(model or "chat model"))
        serialized_messages = [[_payload(message) for message in batch] for batch in messages]
        self._start(
            run_id=run_id,
            parent_run_id=parent_run_id,
            kind="llm",
            name=name,
            attributes={
                "name": name,
                "framework": "langgraph",
                "run_id": str(run_id),
                "provider": provider,
                "model": model,
            },
            input={"messages": serialized_messages},
        )

    def on_llm_end(self, response: Any, *, run_id: uuid.UUID, **_: Any) -> None:
        llm_output = _value(response, "llm_output", {}) or {}
        usage_source: dict[str, Any] = {}
        if isinstance(llm_output, dict):
            usage_source = (
                llm_output.get("token_usage")
                or llm_output.get("usage")
                or llm_output.get("usage_metadata")
                or {}
            )
        usage = None
        if isinstance(usage_source, dict):
            usage = {
                key: value
                for key, value in {
                    "input_tokens": usage_source.get(
                        "prompt_tokens", usage_source.get("input_tokens")
                    ),
                    "output_tokens": usage_source.get(
                        "completion_tokens", usage_source.get("output_tokens")
                    ),
                    "cached_tokens": usage_source.get("cached_tokens"),
                    "total_tokens": usage_source.get("total_tokens"),
                }.items()
                if value is not None
            }
        self._finish(run_id=run_id, output=_payload(response), usage=usage or None)

    def on_llm_error(self, error: BaseException, *, run_id: uuid.UUID, **_: Any) -> None:
        self._finish(run_id=run_id, error=error)

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        inputs: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        name = _name(serialized, "tool")
        self._start(
            run_id=run_id,
            parent_run_id=parent_run_id,
            kind="tool",
            name=name,
            attributes={
                "name": name,
                "protocol": "function",
                "framework": "langgraph",
                "run_id": str(run_id),
                "langgraph_node": (metadata or {}).get("langgraph_node"),
            },
            input={"arguments": inputs if inputs is not None else input_str},
        )

    def on_tool_end(self, output: Any, *, run_id: uuid.UUID, **_: Any) -> None:
        self._finish(run_id=run_id, output=_payload(output))

    def on_tool_error(self, error: BaseException, *, run_id: uuid.UUID, **_: Any) -> None:
        self._finish(run_id=run_id, error=error)

    def on_retry(
        self,
        retry_state: Any,
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        **_: Any,
    ) -> None:
        with self._lock:
            run = self._runs.get(run_id)
        outcome = _value(retry_state, "outcome")
        exception = None
        if outcome is not None and callable(_value(outcome, "exception")):
            try:
                exception = outcome.exception()
            except Exception:
                exception = None
        self._emit(
            "graph.retry",
            status="ok",
            span_id=run.span_id if run else self.graph_span_id,
            parent_span_id=(run.parent_span_id if run else self._parent_span(parent_run_id)),
            attributes={
                "name": run.name if run else "retry",
                "framework": "langgraph",
                "run_id": str(run_id),
                "attempt": _value(retry_state, "attempt_number"),
                "error_type": type(exception).__name__ if exception else None,
                "error_message": str(exception) if exception else None,
            },
        )

    def on_interrupt(self, event: Any) -> None:
        self._record_interrupts(
            list(_value(event, "interrupts", ()) or ()),
            checkpoint_id=_value(event, "checkpoint_id"),
            checkpoint_namespace=_value(event, "checkpoint_ns"),
            status=_value(event, "status"),
        )

    def _record_interrupts(
        self,
        interrupts: list[Any],
        *,
        checkpoint_id: str | None = None,
        checkpoint_namespace: Any = None,
        status: Any = None,
    ) -> None:
        if self.interrupted:
            return
        self.interrupted = True
        self._emit(
            "graph.interrupted",
            status="cancelled",
            span_id=self.graph_span_id,
            attributes={
                "framework": "langgraph",
                "checkpoint_id": checkpoint_id,
                "checkpoint_namespace": checkpoint_namespace,
                "lifecycle_status": status,
                "interrupts": [
                    {"id": _value(item, "id"), "value": _value(item, "value")}
                    for item in interrupts
                ],
            },
        )

    def on_resume(self, event: Any) -> None:
        if self.resumed:
            return
        self.resumed = True
        self._emit(
            "graph.resumed",
            status="ok",
            span_id=self.graph_span_id,
            attributes={
                "framework": "langgraph",
                "checkpoint_id": _value(event, "checkpoint_id"),
                "checkpoint_namespace": _value(event, "checkpoint_ns"),
                "lifecycle_status": _value(event, "status"),
            },
        )

    def record_result_interrupts(self, result: Any) -> None:
        interrupts = _interrupts_from_result(result)
        if interrupts:
            self._record_interrupts(interrupts)

    def record_resume_input(self, input: Any) -> None:
        resume = _resume_value(input)
        if resume is None or self.resumed:
            return
        self.resumed = True
        self._emit(
            "graph.resumed",
            status="ok",
            span_id=self.graph_span_id,
            attributes={"framework": "langgraph", "source": "Command.resume"},
            input={"resume": resume} if isinstance(resume, dict) else {"resume": str(resume)},
        )


class ObservedGraph:
    """A transparent invoke/ainvoke wrapper with per-invocation trace state."""

    def __init__(
        self,
        graph: Any,
        session: VoiceSession | None = None,
        *,
        agent: str = "langgraph-agent",
        version: str | None = None,
        client: VokerVoice | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.graph = graph
        self.session = session
        self.agent = agent
        self.version = version
        self.client = client
        self.session_id = session_id
        self.metadata = metadata or {}
        self._paused_session: VoiceSession | None = None

    def _session_for_call(self, config: dict[str, Any] | None) -> tuple[VoiceSession, bool]:
        active = current_session()
        if self.session is not None:
            return self.session, False
        if active is not None:
            return active, False
        if self._paused_session is not None:
            return self._paused_session, True
        configurable = (config or {}).get("configurable") or {}
        thread_id = configurable.get("thread_id") if isinstance(configurable, dict) else None
        client = self.client or VokerVoice()
        session = client.session(
            agent=self.agent,
            version=self.version,
            session_id=self.session_id or (str(thread_id) if thread_id is not None else None),
            metadata={"integration": "langgraph", **self.metadata},
        )
        session.emit(
            "session.started",
            status="ok",
            source={"integration": "langgraph"},
            attributes=session.metadata,
        )
        self._paused_session = session
        return session, True

    def _finish_owned_session(
        self, session: VoiceSession, error: BaseException | None = None
    ) -> None:
        status = status_for_exception(error)
        error_payload = session._error_payload(error) if error is not None else None
        if error_payload is not None:
            session.emit(
                "session.error",
                status=status,
                source={"integration": "langgraph"},
                error=error_payload,
                attributes=session.metadata,
            )
        session.emit(
            "session.ended",
            status=status,
            source={"integration": "langgraph"},
            error=error_payload,
            attributes=session.metadata,
        )
        session.client.flush(timeout=session.client.session_flush_timeout)
        if self._paused_session is session:
            self._paused_session = None

    async def _finish_owned_session_async(
        self, session: VoiceSession, error: BaseException | None = None
    ) -> None:
        status = status_for_exception(error)
        error_payload = session._error_payload(error) if error is not None else None
        if error_payload is not None:
            session.emit(
                "session.error",
                status=status,
                source={"integration": "langgraph"},
                error=error_payload,
                attributes=session.metadata,
            )
        session.emit(
            "session.ended",
            status=status,
            source={"integration": "langgraph"},
            error=error_payload,
            attributes=session.metadata,
        )
        await session.client.aflush(timeout=session.client.session_flush_timeout)
        if self._paused_session is session:
            self._paused_session = None

    def _graph_name(self) -> str:
        get_name = getattr(self.graph, "get_name", None)
        if callable(get_name):
            try:
                return str(get_name())
            except Exception:
                pass
        return type(self.graph).__name__

    def _config(
        self,
        config: dict[str, Any] | None,
        callback: VokerLangGraphCallback,
    ) -> dict[str, Any]:
        merged = dict(config or {})
        callbacks = list(merged.get("callbacks") or [])
        callbacks.append(callback)
        merged["callbacks"] = callbacks
        return merged

    def _start_invocation(
        self, session: VoiceSession, input: Any
    ) -> tuple[VokerLangGraphCallback, str, str, str | None, str | None]:
        graph_span_id = new_id("spn")
        agent_run_id = new_id("run")
        parent_span_id = current_span_id()
        turn_id = current_turn_id()
        parent_agent_run_id = current_agent_run_id()
        graph_name = self._graph_name()
        session.emit(
            "agent.started",
            status="unset",
            source={"integration": "langgraph"},
            turn_id=turn_id,
            agent_run_id=agent_run_id,
            parent_agent_run_id=parent_agent_run_id,
            agent_name=self.agent,
            agent_version=self.version,
            attributes={"semantic_agent": self.agent, "framework": "langgraph"},
        )
        session.emit(
            "graph.started",
            status="unset",
            source={"integration": "langgraph"},
            span_id=graph_span_id,
            parent_span_id=parent_span_id,
            turn_id=turn_id,
            agent_run_id=agent_run_id,
            agent_name=self.agent,
            agent_version=self.version,
            attributes={"name": graph_name, "framework": "langgraph"},
            input=_payload(input),
        )
        callback = VokerLangGraphCallback(
            session,
            graph_span_id=graph_span_id,
            turn_id=turn_id,
            agent_run_id=agent_run_id,
            agent_name=self.agent,
            agent_version=self.version,
        )
        callback.record_resume_input(input)
        return callback, graph_span_id, agent_run_id, parent_span_id, parent_agent_run_id

    def _finish_invocation(
        self,
        session: VoiceSession,
        callback: VokerLangGraphCallback,
        *,
        graph_span_id: str,
        agent_run_id: str,
        parent_span_id: str | None,
        parent_agent_run_id: str | None,
        started: float,
        result: Any = None,
        error: BaseException | None = None,
    ) -> None:
        callback.record_result_interrupts(result)
        graph_name = self._graph_name()
        duration_ms = (time.monotonic() - started) * 1000
        if error is not None and _is_graph_interrupt(error):
            if not callback.interrupted:
                interrupts = list(error.args[0]) if error.args else []
                callback._record_interrupts(interrupts)
            status = "cancelled"
        elif error is not None:
            status = status_for_exception(error)
            session.emit(
                "graph.error",
                status=status,
                source={"integration": "langgraph"},
                span_id=graph_span_id,
                parent_span_id=parent_span_id,
                turn_id=callback.turn_id,
                agent_run_id=agent_run_id,
                agent_name=self.agent,
                agent_version=self.version,
                attributes={
                    "name": graph_name,
                    "framework": "langgraph",
                    "error_category": _error_category(error),
                },
                error=session._error_payload(error),
                duration_ms=duration_ms,
            )
        elif callback.interrupted:
            status = "cancelled"
        else:
            status = "ok"
            session.emit(
                "graph.completed",
                status="ok",
                source={"integration": "langgraph"},
                span_id=graph_span_id,
                parent_span_id=parent_span_id,
                turn_id=callback.turn_id,
                agent_run_id=agent_run_id,
                agent_name=self.agent,
                agent_version=self.version,
                attributes={"name": graph_name, "framework": "langgraph"},
                output=_payload(result),
                duration_ms=duration_ms,
            )
        agent_error = (
            session._error_payload(error) if error is not None and status != "cancelled" else None
        )
        session.emit(
            "agent.error" if agent_error is not None else "agent.completed",
            status=status,
            source={"integration": "langgraph"},
            turn_id=callback.turn_id,
            agent_run_id=agent_run_id,
            parent_agent_run_id=parent_agent_run_id,
            agent_name=self.agent,
            agent_version=self.version,
            attributes={"semantic_agent": self.agent, "framework": "langgraph"},
            error=agent_error,
        )

    def invoke(self, input: Any, config: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        session, owns_session = self._session_for_call(config)
        return self._invoke_bound(session, input, config, kwargs, owns_session=owns_session)

    def _invoke_bound(
        self,
        session: VoiceSession,
        input: Any,
        config: dict[str, Any] | None,
        kwargs: dict[str, Any],
        *,
        owns_session: bool,
    ) -> Any:
        callback, graph_span_id, agent_run_id, parent_span_id, parent_run_id = (
            self._start_invocation(session, input)
        )
        started = time.monotonic()
        result = None
        error: BaseException | None = None
        try:
            with session.activate(
                span_id=graph_span_id,
                turn_id=callback.turn_id,
                agent_run_id=agent_run_id,
                agent_name=self.agent,
                agent_version=self.version,
            ):
                result = self.graph.invoke(input, config=self._config(config, callback), **kwargs)
            return result
        except BaseException as caught:
            error = caught
            raise
        finally:
            self._finish_invocation(
                session,
                callback,
                graph_span_id=graph_span_id,
                agent_run_id=agent_run_id,
                parent_span_id=parent_span_id,
                parent_agent_run_id=parent_run_id,
                started=started,
                result=result,
                error=error,
            )
            if owns_session and not callback.interrupted:
                self._finish_owned_session(session, error)

    async def ainvoke(self, input: Any, config: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        session, owns_session = self._session_for_call(config)
        return await self._ainvoke_bound(session, input, config, kwargs, owns_session=owns_session)

    async def _ainvoke_bound(
        self,
        session: VoiceSession,
        input: Any,
        config: dict[str, Any] | None,
        kwargs: dict[str, Any],
        *,
        owns_session: bool,
    ) -> Any:
        callback, graph_span_id, agent_run_id, parent_span_id, parent_run_id = (
            self._start_invocation(session, input)
        )
        started = time.monotonic()
        result = None
        error: BaseException | None = None
        try:
            async with session.activate(
                span_id=graph_span_id,
                turn_id=callback.turn_id,
                agent_run_id=agent_run_id,
                agent_name=self.agent,
                agent_version=self.version,
            ):
                result = await self.graph.ainvoke(
                    input, config=self._config(config, callback), **kwargs
                )
            return result
        except BaseException as caught:
            error = caught
            raise
        finally:
            self._finish_invocation(
                session,
                callback,
                graph_span_id=graph_span_id,
                agent_run_id=agent_run_id,
                parent_span_id=parent_span_id,
                parent_agent_run_id=parent_run_id,
                started=started,
                result=result,
                error=error,
            )
            if owns_session and not callback.interrupted:
                await self._finish_owned_session_async(session, error)

    def close(self) -> None:
        """Finish an owned graph session that remains paused and will not resume."""

        if self._paused_session is not None:
            self._finish_owned_session(
                self._paused_session,
                asyncio.CancelledError("Paused LangGraph execution was closed"),
            )

    def __getattr__(self, name: str) -> Any:
        """Preserve access to graph APIs not wrapped by this milestone."""

        return getattr(self.graph, name)


def observe(
    graph: Any,
    session: VoiceSession | None = None,
    *,
    agent: str = "langgraph-agent",
    version: str | None = None,
    client: VokerVoice | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ObservedGraph:
    """Return a transparent graph wrapper supporting owned or active sessions."""

    return ObservedGraph(
        graph,
        session,
        agent=agent,
        version=version,
        client=client,
        session_id=session_id,
        metadata=metadata,
    )
