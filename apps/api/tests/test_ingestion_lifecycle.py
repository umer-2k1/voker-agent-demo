from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from voker_voice import MemoryEventSink, VokerVoice, observe_livekit
from voker_voice_api.database import Base
from voker_voice_api.ingestion import IngestContext, persist_event
from voker_voice_api.models import (
    AgentRun,
    AgentVersion,
    Environment,
    Finding,
    Job,
    Organization,
    OrganizationMember,
    Project,
    Span,
    User,
)
from voker_voice_api.models import Session as VoiceSession
from voker_voice_api.routers.dashboard import get_session_trace, list_sessions, project_setup
from voker_voice_api.schemas import CanonicalEvent
from voker_voice_api.worker import reconcile_stale_sessions


def database() -> tuple[Session, IngestContext]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    organization = Organization(name="Lifecycle Test")
    db.add(organization)
    db.flush()
    user = User(email="lifecycle@example.test")
    db.add(user)
    db.flush()
    db.add(
        OrganizationMember(
            organization_id=organization.id,
            user_id=user.id,
            role="owner",
        )
    )
    project = Project(organization_id=organization.id, name="Voice", slug="voice")
    db.add(project)
    db.flush()
    environment = Environment(
        project_id=project.id,
        name="Test",
        slug="test",
        kind="development",
    )
    db.add(environment)
    db.flush()
    return db, IngestContext(
        resolved_project_id=project.id,
        resolved_environment_id=environment.id,
    )


def event(
    event_id: str, event_type: str, occurred_at: datetime, **values: object
) -> CanonicalEvent:
    payload: dict[str, object] = {
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "external_session_id": "call-1",
        "trace_id": "trace-1",
        "status": "ok",
    }
    payload.update(values)
    return CanonicalEvent.model_validate(payload)


def test_out_of_order_span_keeps_terminal_state_and_repairs_start_time() -> None:
    db, context = database()
    started_at = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)
    persist_event(
        db,
        context,
        event(
            "evt-completed",
            "llm.completed",
            started_at + timedelta(seconds=2),
            span_id="span-1",
            status="ok",
            duration_ms=1000,
        ),
    )
    persist_event(
        db,
        context,
        event(
            "evt-started",
            "llm.started",
            started_at + timedelta(seconds=1),
            span_id="span-1",
            status="unset",
        ),
    )

    span = db.scalar(select(Span).where(Span.external_span_id == "span-1"))
    assert span is not None
    assert span.status == "ok"
    assert span.started_at.replace(tzinfo=UTC) == started_at + timedelta(seconds=1)
    assert span.ended_at is not None
    assert span.ended_at.replace(tzinfo=UTC) == started_at + timedelta(seconds=2)
    assert float(span.duration_ms) == 1000


def test_graph_interrupt_closes_the_invocation_span() -> None:
    db, context = database()
    started_at = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)
    persist_event(
        db,
        context,
        event(
            "evt-graph-started",
            "graph.started",
            started_at,
            status="unset",
            span_id="graph-span",
        ),
    )
    persist_event(
        db,
        context,
        event(
            "evt-graph-interrupted",
            "graph.interrupted",
            started_at + timedelta(seconds=1),
            status="cancelled",
            span_id="graph-span",
        ),
    )

    span = db.scalar(select(Span).where(Span.external_span_id == "graph-span"))
    assert span is not None
    assert span.status == "cancelled"
    assert span.ended_at is not None
    assert span.ended_at.replace(tzinfo=UTC) == started_at + timedelta(seconds=1)


def test_failed_session_remains_failed_and_queues_analysis_once() -> None:
    db, context = database()
    ended_at = datetime(2026, 9, 21, 10, 1, tzinfo=UTC)
    error = {"type": "ProviderError", "message": "Provider failed"}
    persist_event(
        db,
        context,
        event("evt-end-1", "session.ended", ended_at, status="error", error=error),
    )
    persist_event(
        db,
        context,
        event(
            "evt-start-1",
            "session.started",
            ended_at - timedelta(minutes=1),
            status="ok",
            attributes={"tenant": "demo"},
        ),
    )
    persist_event(
        db,
        context,
        event(
            "evt-end-2",
            "session.ended",
            ended_at + timedelta(seconds=1),
            status="error",
            error=error,
        ),
    )

    session = db.scalar(select(VoiceSession))
    assert session is not None
    assert session.status == "failed"
    assert session.started_at.replace(tzinfo=UTC) == ended_at - timedelta(minutes=1)
    assert session.ended_at is not None
    assert session.ended_at.replace(tzinfo=UTC) == ended_at + timedelta(seconds=1)
    assert session.metadata_ == {"tenant": "demo"}
    assert len(list(db.scalars(select(Job)))) == 2


def test_stalled_session_is_marked_incomplete_and_queues_analysis() -> None:
    db, context = database()
    started_at = datetime.now(UTC) - timedelta(minutes=5)
    persist_event(db, context, event("evt-stalled", "session.started", started_at))
    db.flush()

    reconciled = reconcile_stale_sessions(db, now=datetime.now(UTC) + timedelta(minutes=5))

    session = db.scalar(select(VoiceSession))
    assert reconciled == 1
    assert session is not None
    assert session.status == "incomplete"
    assert session.ended_at is not None
    assert len(list(db.scalars(select(Job)))) == 2


def test_agent_version_and_out_of_order_parent_run_are_repaired() -> None:
    db, context = database()
    timestamp = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)
    identity = {"name": "billing-agent", "version": "2.1"}
    persist_event(
        db,
        context,
        event(
            "evt-child",
            "agent.completed",
            timestamp + timedelta(seconds=2),
            agent=identity,
            agent_run_id="child-run",
            parent_agent_run_id="parent-run",
        ),
    )
    persist_event(
        db,
        context,
        event(
            "evt-parent",
            "agent.started",
            timestamp,
            status="unset",
            agent=identity,
            agent_run_id="parent-run",
        ),
    )

    runs = list(db.scalars(select(AgentRun).order_by(AgentRun.started_at)))
    child = next(item for item in runs if item.external_run_id == "child-run")
    parent = next(item for item in runs if item.external_run_id == "parent-run")
    assert child.parent_run_id == parent.id
    assert child.status == "ok"
    assert child.ended_at is not None
    assert child.ended_at.replace(tzinfo=UTC) == timestamp + timedelta(seconds=2)
    assert db.scalar(select(AgentVersion).where(AgentVersion.version == "2.1")) is not None


def test_sdk_generated_trace_is_accepted_by_api_contract() -> None:
    db, context = database()
    sink = MemoryEventSink()
    client = VokerVoice(enabled=True, event_sink=sink)

    with client.session(agent="support", version="1.2", session_id="call-1") as call:
        with call.turn(speaker="user", transcript="Where is my order?"):
            with call.agent("orders", version="2.0"):
                with call.span("llm", provider="openrouter"):
                    with call.tool("lookup_order", protocol="mcp") as tool:
                        tool.set_output({"order_status": "shipped"})
        call.record_outcome("resolved")

    for payload in sink.events:
        assert persist_event(db, context, CanonicalEvent.model_validate(payload)) == "accepted"

    session = db.scalar(select(VoiceSession))
    assert session is not None
    assert session.status == "completed"
    assert session.outcome == "resolved"
    assert len(list(db.scalars(select(Span)))) == 2
    assert len(list(db.scalars(select(AgentRun)))) == 1


def test_livekit_generated_voice_pipeline_is_accepted_and_nested() -> None:
    class FakeAgentSession:
        def __init__(self) -> None:
            self.handlers: dict[str, object] = {}
            self.current_speech: dict[str, object] | None = None

        def on(self, name: str, callback: object) -> None:
            self.handlers[name] = callback

        def off(self, name: str, callback: object) -> None:
            if self.handlers.get(name) is callback:
                del self.handlers[name]

        def emit(self, name: str, payload: object) -> None:
            callback = self.handlers[name]
            assert callable(callback)
            callback(payload)

    db, context = database()
    sink = MemoryEventSink()
    fake = FakeAgentSession()
    client = VokerVoice(enabled=True, event_sink=sink)
    observe_livekit(fake, agent="support", client=client, session_id="call-1")
    timestamp = datetime(2026, 9, 21, 10, 0, tzinfo=UTC).timestamp()
    fake.emit(
        "user_state_changed",
        {"old_state": "listening", "new_state": "speaking", "created_at": timestamp},
    )
    fake.emit(
        "user_input_transcribed",
        {
            "transcript": "Where is my order?",
            "is_final": True,
            "item_id": "user-1",
            "created_at": timestamp + 0.5,
        },
    )
    fake.emit(
        "metrics_collected",
        {
            "metrics": {
                "type": "llm_metrics",
                "request_id": "llm-1",
                "timestamp": timestamp + 1.5,
                "duration": 0.8,
                "ttft": 0.2,
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "cancelled": False,
                "metadata": {"model_provider": "openai", "model_name": "gpt-test"},
            }
        },
    )
    fake.emit(
        "tool_execution_updated",
        {
            "created_at": timestamp + 1.6,
            "update": {
                "type": "tool_call_started",
                "function_call": {
                    "call_id": "tool-1",
                    "name": "lookup_order",
                    "arguments": '{"order_id":"123"}',
                },
            },
        },
    )
    fake.emit(
        "tool_execution_updated",
        {
            "created_at": timestamp + 1.8,
            "update": {
                "type": "tool_call_ended",
                "call_id": "tool-1",
                "status": "done",
                "message": "shipped",
            },
        },
    )
    speech = {"id": "speech-1", "interrupted": False}
    fake.current_speech = speech
    fake.emit(
        "speech_created",
        {
            "created_at": timestamp + 1.9,
            "speech_handle": speech,
            "source": "generate_reply",
            "user_initiated": False,
        },
    )
    fake.emit(
        "metrics_collected",
        {
            "metrics": {
                "type": "tts_metrics",
                "request_id": "tts-1",
                "speech_id": "speech-1",
                "timestamp": timestamp + 2.2,
                "duration": 0.3,
                "ttfb": 0.1,
                "audio_duration": 1.0,
                "characters_count": 18,
                "cancelled": False,
                "metadata": {"model_provider": "cartesia", "model_name": "sonic"},
            }
        },
    )
    fake.emit(
        "conversation_item_added",
        {
            "created_at": timestamp + 2.3,
            "item": {
                "type": "message",
                "id": "assistant-1",
                "role": "assistant",
                "content": ["Your order shipped"],
            },
        },
    )
    fake.emit(
        "agent_state_changed",
        {"old_state": "thinking", "new_state": "speaking", "created_at": timestamp + 2.4},
    )
    fake.emit(
        "agent_state_changed",
        {"old_state": "speaking", "new_state": "listening", "created_at": timestamp + 3.4},
    )
    fake.emit(
        "close",
        {"created_at": timestamp + 3.5, "reason": "task_completed", "error": None},
    )

    for payload in sink.events:
        assert persist_event(db, context, CanonicalEvent.model_validate(payload)) == "accepted"

    voice_session = db.scalar(select(VoiceSession))
    assert voice_session is not None
    assert voice_session.status == "completed"
    spans = list(db.scalars(select(Span)))
    assert {span.kind for span in spans} >= {"stt", "llm", "tool", "tts", "playback"}
    playback = next(span for span in spans if span.kind == "playback")
    tts_span = next(span for span in spans if span.kind == "tts")
    assert playback.parent_span_id == tts_span.id
    assert all(span.turn_id is not None for span in spans)
    assert all(span.agent_run_id is not None for span in spans)
    dashboard_user = db.scalar(select(User))
    assert dashboard_user is not None
    trace = get_session_trace("voice", voice_session.id, dashboard_user, db, event_limit=3)
    assert trace["session"]["status"] == "completed"
    assert trace["event_page"]["total"] > len(trace["events"])
    assert len(trace["events"]) == 3
    assert trace["agent_runs"]
    assert set(trace["voice_behavior"]) == {
        "interruptions",
        "talk_over",
        "dead_air",
        "corrections",
        "abandonment",
    }
    assert {span["kind"] for span in trace["spans"]} >= {
        "stt",
        "llm",
        "tool",
        "tts",
        "playback",
    }
    llm_span = next(span for span in trace["spans"] if span["kind"] == "llm")
    assert llm_span["duration_ms"] == 800
    assert llm_span["attributes"]["provider"] == "openai"
    assert trace["tool_summary"] == {"total": 1, "succeeded": 1, "failed": 0}
    assert trace["tool_calls"][0]["name"] == "lookup_order"
    assert trace["tool_calls"][0]["input"] == {"arguments": {"order_id": "123"}}
    assert trace["tool_calls"][0]["output"] == {"result": "shipped"}
    filtered = list_sessions(
        "voice",
        dashboard_user,
        status="completed",
        source="livekit",
        environment="test",
        has_error=False,
        started_after=datetime(2026, 9, 21, 9, 59, tzinfo=UTC),
        started_before=datetime(2026, 9, 21, 10, 1, tzinfo=UTC),
        min_latency_ms=100,
        search="call-1",
        db=db,
    )
    assert filtered["page"]["total"] == 1
    assert filtered["items"][0]["environment"] == "test"
    assert filtered["items"][0]["agent"] == "support"
    setup = project_setup("voice", dashboard_user, db)
    assert setup["last_received_event_at"] is not None
    assert {"stt", "llm", "tool", "tts", "playback"} <= set(setup["observed_stages"])


def test_trace_marks_a_legacy_session_with_sequence_gaps_as_incomplete() -> None:
    db, context = database()
    started_at = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)
    persist_event(
        db,
        context,
        event("evt-start", "session.started", started_at, sequence=1),
    )
    persist_event(
        db,
        context,
        event(
            "evt-end",
            "session.ended",
            started_at + timedelta(seconds=5),
            sequence=4,
            attributes={"expected_last_sequence": 4},
        ),
    )
    session = db.scalar(select(VoiceSession))
    user = db.scalar(select(User))
    assert session is not None
    assert user is not None

    trace = get_session_trace("voice", session.id, user, db)

    assert trace["collection"]["capture_state"] == "incomplete"
    assert trace["collection"]["highest_seen_sequence"] == 4
    assert trace["collection"]["highest_contiguous_sequence"] == 1
    assert trace["collection"]["expected_last_sequence"] == 4
    assert trace["collection"]["missing_ranges"] == [[2, 3]]


def test_trace_reconciles_dead_air_count_with_evidence_backed_findings() -> None:
    db, context = database()
    started_at = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)
    persist_event(
        db,
        context,
        event("evt-start", "session.started", started_at, sequence=1),
    )
    persist_event(
        db,
        context,
        event("evt-end", "session.ended", started_at + timedelta(seconds=5), sequence=2),
    )
    session = db.scalar(select(VoiceSession))
    user = db.scalar(select(User))
    assert session is not None
    assert user is not None
    db.add(
        Finding(
            session_id=session.id,
            type="dead_air",
            certainty="detected_condition",
            severity="medium",
            statement="The response gap was 3000 ms.",
            rule_id="response-gap:test",
            rule_version="2",
            attributes={"observed_value": 3000, "threshold": 2500},
        )
    )
    db.flush()

    trace = get_session_trace("voice", session.id, user, db)

    assert trace["voice_behavior"]["dead_air"] == 1
    assert trace["voice_behavior_sources"]["dead_air"] == {
        "source": "speech.stopped → playback.started",
        "threshold_ms": 2500.0,
        "method": "deterministic response-gap rule",
    }


def test_trace_identifier_is_scoped_by_project_and_environment() -> None:
    first_db, first_context = database()
    organization = first_db.scalar(select(Organization))
    assert organization is not None
    second_project = Project(
        organization_id=organization.id,
        name="Second Voice",
        slug="second-voice",
    )
    first_db.add(second_project)
    first_db.flush()
    second_environment = Environment(
        project_id=second_project.id,
        name="Test",
        slug="test",
        kind="development",
    )
    first_db.add(second_environment)
    first_db.flush()
    second_context = IngestContext(
        resolved_project_id=second_project.id,
        resolved_environment_id=second_environment.id,
    )
    timestamp = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)

    persist_event(first_db, first_context, event("evt-first", "session.started", timestamp))
    persist_event(first_db, second_context, event("evt-second", "session.started", timestamp))
    first_db.flush()

    assert len(list(first_db.scalars(select(VoiceSession)))) == 2
