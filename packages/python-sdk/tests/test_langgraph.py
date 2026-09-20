import pytest

from voker_voice import MemoryEventSink, VokerVoice, observe_langgraph


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
