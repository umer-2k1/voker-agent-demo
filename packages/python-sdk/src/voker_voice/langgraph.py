"""LangGraph integration built on LangChain's public callback protocol."""

import time
import uuid
from typing import Any

try:
    from langchain_core.callbacks import BaseCallbackHandler
except ImportError:  # pragma: no cover - optional dependency guard
    BaseCallbackHandler = object  # type: ignore[assignment,misc]

from voker_voice.context import VoiceSession


class VokerLangGraphCallback(BaseCallbackHandler):
    """Maps LangGraph chain/node callbacks into nested canonical graph spans."""

    def __init__(self, session: VoiceSession) -> None:
        self.session = session
        self._runs: dict[uuid.UUID, tuple[str, str | None, float, str]] = {}

    def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any],
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        **_: Any,
    ) -> None:
        descriptor = serialized or {}
        identifier = descriptor.get("id") or ["graph"]
        name = str(descriptor.get("name") or identifier[-1])
        span_id = f"lg_{run_id.hex}"
        parent_span_id = self._runs[parent_run_id][0] if parent_run_id in self._runs else None
        self._runs[run_id] = (span_id, parent_span_id, time.monotonic(), name)
        self.session.emit(
            "graph.node.started",
            span_id=span_id,
            parent_span_id=parent_span_id,
            attributes={"name": name, "framework": "langgraph", "run_id": str(run_id)},
            input=inputs,
        )
        if parent_run_id in self._runs:
            parent_name = self._runs[parent_run_id][3]
            if parent_name != name:
                self.session.handoff(
                    from_agent=parent_name,
                    to_agent=name,
                    reason="LangGraph graph transition",
                )

    def on_chain_end(self, outputs: dict[str, Any], *, run_id: uuid.UUID, **_: Any) -> None:
        run = self._runs.pop(run_id, None)
        if run is None:
            return
        span_id, parent_span_id, started, name = run
        self.session.emit(
            "graph.node.completed",
            status="ok",
            span_id=span_id,
            parent_span_id=parent_span_id,
            attributes={"name": name, "framework": "langgraph", "run_id": str(run_id)},
            output=outputs,
            duration_ms=(time.monotonic() - started) * 1000,
        )

    def on_chain_error(self, error: BaseException, *, run_id: uuid.UUID, **_: Any) -> None:
        run = self._runs.pop(run_id, None)
        if run is None:
            return
        span_id, parent_span_id, started, name = run
        self.session.emit(
            "graph.node.error",
            status="error",
            span_id=span_id,
            parent_span_id=parent_span_id,
            attributes={"name": name, "framework": "langgraph", "run_id": str(run_id)},
            error=self.session._error_payload(error),
            duration_ms=(time.monotonic() - started) * 1000,
        )

    def on_retry(self, retry_state: Any, *, run_id: uuid.UUID, **_: Any) -> None:
        """Record callback retries without changing LangGraph retry behavior."""

        run = self._runs.get(run_id)
        if run is None:
            return
        span_id, parent_span_id, _, name = run
        self.session.emit(
            "graph.node.retry",
            status="ok",
            span_id=span_id,
            parent_span_id=parent_span_id,
            attributes={
                "name": name,
                "framework": "langgraph",
                "run_id": str(run_id),
                "retry_state": str(retry_state),
            },
        )


class ObservedGraph:
    def __init__(self, graph: Any, session: VoiceSession) -> None:
        self.graph = graph
        self.session = session
        self.callback = VokerLangGraphCallback(session)

    def _config(self, config: dict[str, Any] | None) -> dict[str, Any]:
        merged = dict(config or {})
        callbacks = list(merged.get("callbacks") or [])
        callbacks.append(self.callback)
        merged["callbacks"] = callbacks
        return merged

    def invoke(self, input: Any, config: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        try:
            return self.graph.invoke(input, config=self._config(config), **kwargs)
        except BaseException as error:
            self._record_interrupt(error)
            raise

    async def ainvoke(self, input: Any, config: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        try:
            return await self.graph.ainvoke(input, config=self._config(config), **kwargs)
        except BaseException as error:
            self._record_interrupt(error)
            raise

    def _record_interrupt(self, error: BaseException) -> None:
        if "interrupt" not in type(error).__name__.lower():
            return
        self.session.emit(
            "graph.interrupted",
            status="cancelled",
            attributes={
                "framework": "langgraph",
                "interrupt_type": type(error).__name__,
                "message": str(error),
            },
        )


def observe(graph: Any, session: VoiceSession) -> ObservedGraph:
    """Return a graph wrapper; callers retain normal invoke/ainvoke semantics."""
    return ObservedGraph(graph, session)
