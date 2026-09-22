import operator
from typing import Annotated, TypedDict
from uuid import uuid4

import pytest

from voker_voice import (
    MemoryEventSink,
    VokerVoice,
    current_session,
    observe_langgraph,
)
from voker_voice.langgraph import VokerLangGraphCallback
from voker_voice_api.schemas import CanonicalEvent


def types(sink: MemoryEventSink) -> list[str]:
    for event in sink.events:
        CanonicalEvent.model_validate(event)
    return [event["event_type"] for event in sink.events]


def test_wrapper_records_graph_and_nodes_without_false_handoffs() -> None:
    pytest.importorskip("langgraph")
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(dict)
    graph.add_node("router", lambda state: {**state, "route": "specialist"})
    graph.add_node("specialist", lambda state: {**state, "answer": "done"})
    graph.add_edge(START, "router")
    graph.add_edge("router", "specialist")
    graph.add_edge("specialist", END)
    sink = MemoryEventSink()
    client = VokerVoice(event_sink=sink, enabled=True)

    with client.session(agent="voice-router", session_id="langgraph-test") as session:
        result = observe_langgraph(
            graph.compile(),
            session,
            agent="customer-service",
        ).invoke({})

    assert result["answer"] == "done"
    assert "graph.started" in types(sink)
    assert "graph.completed" in types(sink)
    starts = [event for event in sink.events if event["event_type"] == "graph.node.started"]
    assert [event["attributes"]["name"] for event in starts] == [
        "router",
        "specialist",
    ]
    graph_start = next(event for event in sink.events if event["event_type"] == "graph.started")
    assert all(event["parent_span_id"] == graph_start["span_id"] for event in starts)
    assert "agent.handoff" not in types(sink)
    assert all(event["attributes"]["semantic_agent"] is False for event in starts)


def test_one_call_wrapper_owns_session_and_uses_thread_id() -> None:
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(dict)
    graph.add_node("answer", lambda state: {**state, "answer": "ok"})
    graph.add_edge(START, "answer")
    graph.add_edge("answer", END)
    sink = MemoryEventSink()

    result = observe_langgraph(
        graph.compile(),
        agent="customer-service",
        version="2.0",
        client=VokerVoice(event_sink=sink, enabled=True),
    ).invoke({}, config={"configurable": {"thread_id": "thread-42"}})

    assert result["answer"] == "ok"
    assert types(sink)[0] == "session.started"
    assert types(sink)[-1] == "session.ended"
    assert {event["external_session_id"] for event in sink.events} == {"thread-42"}
    graph_agent = next(
        event
        for event in sink.events
        if event["event_type"] == "agent.started" and event["agent"]["name"] == "customer-service"
    )
    assert graph_agent["agent"]["version"] == "2.0"


@pytest.mark.asyncio
async def test_async_graph_propagates_active_voice_session_and_parent_agent_run() -> None:
    from langgraph.graph import END, START, StateGraph

    seen_sessions = []

    async def specialist(state):
        seen_sessions.append(current_session())
        return {**state, "done": True}

    graph = StateGraph(dict)
    graph.add_node("specialist", specialist)
    graph.add_edge(START, "specialist")
    graph.add_edge("specialist", END)
    sink = MemoryEventSink()
    client = VokerVoice(event_sink=sink, enabled=True)

    async with client.session(agent="voice-agent", session_id="async-graph") as session:
        async with session.agent("triage-agent") as parent:
            result = await observe_langgraph(
                graph.compile(),
                agent="billing-agent",
            ).ainvoke({})

    assert result["done"] is True
    assert seen_sessions == [session]
    billing_start = next(
        event
        for event in sink.events
        if event["event_type"] == "agent.started" and event["agent"]["name"] == "billing-agent"
    )
    assert billing_start["parent_agent_run_id"] == parent.run_id


def test_explicit_handoff_inside_node_is_the_only_semantic_handoff() -> None:
    from langgraph.graph import END, START, StateGraph

    def route(state):
        session = current_session()
        assert session is not None
        session.handoff(
            from_agent="triage-agent",
            to_agent="billing-agent",
            reason="billing_question",
        )
        return {**state, "routed": True}

    graph = StateGraph(dict)
    graph.add_node("router_node", route)
    graph.add_node("billing_node", lambda state: state)
    graph.add_edge(START, "router_node")
    graph.add_edge("router_node", "billing_node")
    graph.add_edge("billing_node", END)
    sink = MemoryEventSink()

    with VokerVoice(event_sink=sink, enabled=True).session(agent="voice-agent") as session:
        observe_langgraph(graph.compile(), session, agent="triage-agent").invoke({})

    handoffs = [event for event in sink.events if event["event_type"] == "agent.handoff"]
    assert len(handoffs) == 1
    assert handoffs[0]["attributes"]["from_agent"] == "triage-agent"
    assert handoffs[0]["attributes"]["to_agent"] == "billing-agent"


def test_callback_records_llm_tools_and_canonical_retry() -> None:
    sink = MemoryEventSink()
    with VokerVoice(event_sink=sink, enabled=True).session(agent="voice-router") as session:
        callback = VokerLangGraphCallback(
            session,
            graph_span_id="graph-span",
            agent_run_id="agent-run",
        )
        node_id = uuid4()
        llm_id = uuid4()
        failed_tool_id = uuid4()
        successful_tool_id = uuid4()
        callback.on_chain_start(
            None,
            {"question": "hello"},
            run_id=node_id,
            parent_run_id=None,
            name="router",
            tags=["graph:step:1"],
            metadata={"langgraph_node": "router", "langgraph_step": 1},
        )
        callback.on_chat_model_start(
            {"name": "ChatModel"},
            [[{"role": "user", "content": "hello"}]],
            run_id=llm_id,
            parent_run_id=node_id,
            metadata={"ls_provider": "openai"},
            invocation_params={"model": "gpt-test"},
        )
        callback.on_llm_end(
            {
                "generations": [["answer"]],
                "llm_output": {
                    "token_usage": {
                        "prompt_tokens": 8,
                        "completion_tokens": 3,
                        "total_tokens": 11,
                    }
                },
            },
            run_id=llm_id,
        )
        callback.on_tool_start(
            {"name": "lookup"},
            '{"id":"1"}',
            run_id=failed_tool_id,
            parent_run_id=node_id,
            inputs={"id": "1"},
        )
        callback.on_tool_error(RuntimeError("temporary"), run_id=failed_tool_id)
        callback.on_retry(
            type("Retry", (), {"attempt_number": 2, "outcome": None})(),
            run_id=failed_tool_id,
            parent_run_id=node_id,
        )
        callback.on_tool_start(
            {"name": "lookup"},
            '{"id":"1"}',
            run_id=successful_tool_id,
            parent_run_id=node_id,
            inputs={"id": "1"},
        )
        callback.on_tool_end({"status": "found"}, run_id=successful_tool_id)
        callback.on_chain_end({"answer": "done"}, run_id=node_id)

    assert "llm.started" in types(sink)
    assert "llm.completed" in types(sink)
    assert "tool.error" in types(sink)
    assert "tool.completed" in types(sink)
    assert "graph.retry" in types(sink)
    llm = next(event for event in sink.events if event["event_type"] == "llm.completed")
    assert llm["usage"]["input_tokens"] == 8
    assert llm["usage"]["output_tokens"] == 3
    assert llm["parent_span_id"].startswith("lg_")


def test_interrupt_and_resume_use_public_langgraph_lifecycle() -> None:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command, interrupt

    class State(TypedDict, total=False):
        approved: bool

    def approval(state: State) -> State:
        approved = interrupt({"question": "Approve?"})
        return {**state, "approved": bool(approved)}

    graph = StateGraph(State)
    graph.add_node("approval", approval)
    graph.add_edge(START, "approval")
    graph.add_edge("approval", END)
    sink = MemoryEventSink()
    observed = observe_langgraph(
        graph.compile(checkpointer=InMemorySaver()),
        agent="approval-agent",
        client=VokerVoice(event_sink=sink, enabled=True),
    )
    config = {"configurable": {"thread_id": "approval-thread"}}

    paused = observed.invoke({}, config=config)
    assert paused["__interrupt__"]
    assert "graph.interrupted" in types(sink)
    assert "graph.node.error" not in types(sink)
    assert "session.ended" not in types(sink)

    resumed = observed.invoke(Command(resume=True), config=config)
    assert resumed["approved"] is True
    assert types(sink).count("graph.resumed") == 1
    assert types(sink).count("session.started") == 1
    assert types(sink).count("session.ended") == 1


def test_recursion_limit_is_classified_and_not_swallowed() -> None:
    from langgraph.errors import GraphRecursionError
    from langgraph.graph import START, StateGraph

    graph = StateGraph(dict)
    graph.add_node("loop", lambda state: state)
    graph.add_edge(START, "loop")
    graph.add_edge("loop", "loop")
    sink = MemoryEventSink()
    observed = observe_langgraph(
        graph.compile(),
        agent="loop-agent",
        client=VokerVoice(event_sink=sink, enabled=True),
    )

    with pytest.raises(GraphRecursionError):
        observed.invoke({}, config={"recursion_limit": 3})

    error = next(event for event in sink.events if event["event_type"] == "graph.error")
    assert error["attributes"]["error_category"] == "recursion_limit"
    assert error["status"] == "error"
    assert types(sink)[-1] == "session.ended"


def test_invalid_node_return_is_classified_and_not_swallowed() -> None:
    from langgraph.errors import InvalidUpdateError
    from langgraph.graph import START, StateGraph

    class State(TypedDict):
        value: str

    graph = StateGraph(State)
    graph.add_node("invalid", lambda _state: ["not", "a", "mapping"])
    graph.add_edge(START, "invalid")
    sink = MemoryEventSink()

    with VokerVoice(event_sink=sink, enabled=True).session(agent="voice") as session:
        with pytest.raises(InvalidUpdateError):
            observe_langgraph(graph.compile(), session).invoke({"value": "start"})

    error = next(event for event in sink.events if event["event_type"] == "graph.error")
    assert error["attributes"]["error_category"] == "invalid_node_return"


def test_parallel_nodes_remain_siblings_under_graph_span() -> None:
    from langgraph.graph import END, START, StateGraph

    class State(TypedDict):
        values: Annotated[list[str], operator.add]

    graph = StateGraph(State)
    graph.add_node("billing", lambda _state: {"values": ["billing"]})
    graph.add_node("calendar", lambda _state: {"values": ["calendar"]})
    graph.add_edge(START, "billing")
    graph.add_edge(START, "calendar")
    graph.add_edge("billing", END)
    graph.add_edge("calendar", END)
    sink = MemoryEventSink()

    with VokerVoice(event_sink=sink, enabled=True).session(agent="voice") as session:
        result = observe_langgraph(graph.compile(), session).invoke({"values": []})

    assert set(result["values"]) == {"billing", "calendar"}
    graph_span = next(event for event in sink.events if event["event_type"] == "graph.started")[
        "span_id"
    ]
    starts = [event for event in sink.events if event["event_type"] == "graph.node.started"]
    assert {event["attributes"]["name"] for event in starts} == {
        "billing",
        "calendar",
    }
    assert {event["parent_span_id"] for event in starts} == {graph_span}
