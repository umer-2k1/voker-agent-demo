from uuid import uuid4

import pytest

from voker_voice import MemoryEventSink, VokerVoice, observe_langgraph
from voker_voice.langgraph import VokerLangGraphCallback


def test_langgraph_wrapper_records_nodes() -> None:
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
        result = observe_langgraph(graph.compile(), session).invoke({})
    assert result["answer"] == "done"
    assert any(event["event_type"] == "graph.node.started" for event in sink.events)
    assert any(event["event_type"] == "graph.node.completed" for event in sink.events)


def test_langgraph_callback_records_handoff_and_retry() -> None:
    sink = MemoryEventSink()
    with VokerVoice(event_sink=sink, enabled=True).session(agent="voice-router") as session:
        callback = VokerLangGraphCallback(session)
        parent = uuid4()
        child = uuid4()
        callback.on_chain_start({"name": "router"}, {}, run_id=parent)
        callback.on_chain_start({"name": "specialist"}, {}, run_id=child, parent_run_id=parent)
        callback.on_retry("retry once", run_id=child)
    handoff = next(event for event in sink.events if event["event_type"] == "agent.handoff")
    assert handoff["attributes"]["from_agent"] == "router"
    assert handoff["attributes"]["to_agent"] == "specialist"
    assert any(event["event_type"] == "graph.node.retry" for event in sink.events)
