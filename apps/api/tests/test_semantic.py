import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from voker_voice_api.analysis import run_deterministic_analysis
from voker_voice_api.config import get_settings
from voker_voice_api.database import Base
from voker_voice_api.models import (
    AnalysisRun,
    Environment,
    Event,
    Finding,
    FindingEvidence,
    Organization,
    Project,
    Span,
    Turn,
)
from voker_voice_api.models import Session as VoiceSession
from voker_voice_api.semantic import (
    build_evaluator_evidence,
    evaluate_session,
    parse_semantic_result,
)


def semantic_json(
    *,
    event_id: str = "evt-1",
    finding_event_id: str | None = None,
) -> str:
    finding_id = finding_event_id or event_id
    return json.dumps(
        {
            "intent": "Check order status",
            "outcome": "success",
            "outcome_source": "inferred",
            "resolution_state": "resolved",
            "failure_category": None,
            "summary": "The order status was returned.",
            "confidence": 0.88,
            "evidence": [{"entity_type": "event", "entity_id": event_id}],
            "findings": [
                {
                    "type": "tool_latency",
                    "statement": "Tool latency was associated with a response delay.",
                    "severity": "medium",
                    "confidence": 0.76,
                    "certainty": "inferred_contributing_factor",
                    "evidence": [
                        {"entity_type": "event", "entity_id": finding_id},
                        {"entity_type": "span", "entity_id": "span-1"},
                        {"entity_type": "turn", "entity_id": "turn-1"},
                    ],
                    "next_step": "Inspect the order lookup span.",
                }
            ],
        }
    )


def database(*, semantic_enabled: bool = True) -> tuple[Session, VoiceSession, Project]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    organization = Organization(name="Intelligence Test")
    db.add(organization)
    db.flush()
    project = Project(
        organization_id=organization.id,
        name="Voice",
        slug=f"voice-{uuid4().hex[:8]}",
        semantic_analysis_enabled=semantic_enabled,
        semantic_content_exclusions=["customer_ssn"],
    )
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
    started = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)
    voice_session = VoiceSession(
        project_id=project.id,
        environment_id=environment.id,
        external_session_id="call-1",
        trace_id=f"trace-{uuid4().hex}",
        source="custom",
        status="completed",
        started_at=started,
        ended_at=started + timedelta(seconds=5),
        metadata_={},
    )
    db.add(voice_session)
    db.flush()
    turn = Turn(
        session_id=voice_session.id,
        external_turn_id="turn-1",
        sequence=1,
        speaker="user",
        started_at=started,
        ended_at=started + timedelta(seconds=4),
        transcript="Where is order 123?",
        attributes={},
    )
    db.add(turn)
    db.flush()
    span = Span(
        session_id=voice_session.id,
        turn_id=turn.id,
        external_span_id="span-1",
        name="lookup_order",
        kind="tool",
        status="ok",
        started_at=started + timedelta(seconds=1),
        ended_at=started + timedelta(seconds=3),
        duration_ms=2000,
        attributes={"customer_ssn": "123-45-6789", "provider": "orders"},
    )
    db.add(span)
    db.flush()
    db.add(
        Event(
            project_id=project.id,
            session_id=voice_session.id,
            span_id=span.id,
            turn_id=turn.id,
            event_id="evt-1",
            event_type="tool.completed",
            sequence=1,
            occurred_at=started + timedelta(seconds=3),
            status="ok",
            duration_ms=2000,
            payload={
                "attributes": {
                    "customer_ssn": "123-45-6789",
                    "authorization": "Bearer hidden",
                }
            },
            raw_payload={"secret": "must-not-be-sent"},
        )
    )
    db.flush()
    return db, voice_session, project


def test_semantic_parser_accepts_fenced_json() -> None:
    result = parse_semantic_result(f"```json\n{semantic_json()}\n```")

    assert result.outcome == "success"
    assert result.intent == "Check order status"
    assert result.findings[0].evidence[1].entity_type == "span"


def test_semantic_parser_normalizes_unambiguous_bare_finding_ids() -> None:
    payload = json.loads(semantic_json(event_id="evt_1", finding_event_id="evt_1"))
    payload["findings"][0]["evidence"] = ["evt_1", "span_1", "turn_1"]

    result = parse_semantic_result(json.dumps(payload))

    assert [(item.entity_type, item.entity_id) for item in result.findings[0].evidence] == [
        ("event", "evt_1"),
        ("span", "span_1"),
        ("turn", "turn_1"),
    ]


def test_evaluator_evidence_is_bounded_redacted_and_omits_raw_receipts() -> None:
    db, voice_session, _project = database()
    events = list(db.scalars(select(Event)))
    spans = list(db.scalars(select(Span)))
    turns = list(db.scalars(select(Turn)))

    evidence = build_evaluator_evidence(
        session=voice_session,
        events=events,
        spans=spans,
        turns=turns,
        exclusions={"authorization", "customer_ssn"},
    )
    encoded = json.dumps(evidence)

    assert "123-45-6789" not in encoded
    assert "Bearer hidden" not in encoded
    assert "must-not-be-sent" not in encoded
    assert encoded.count("[EXCLUDED]") >= 2


def test_semantic_evaluator_persists_metrics_mixed_evidence_and_outcome(
    monkeypatch,
) -> None:
    db, voice_session, _project = database()
    settings = get_settings()
    monkeypatch.setattr(settings, "semantic_evaluator_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_model", "test/model")

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": semantic_json()}}],
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 40,
                    "cost": 0.0015,
                },
            }

    captured = {}

    def post(*_args, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("voker_voice_api.semantic.httpx.post", post)

    created = evaluate_session(db, session_id=voice_session.id)

    assert created == 1
    run = db.scalar(select(AnalysisRun))
    assert run is not None
    assert run.status == "completed"
    assert run.analysis_version == 1
    assert run.schema_version == "2"
    assert run.input_tokens == 120
    assert run.output_tokens == 40
    assert run.cost_micros == 1500
    assert run.evaluator_latency_ms is not None
    assert run.result is not None
    assert run.result["intent"] == "Check order status"
    assert voice_session.metadata_["intent"] == "unknown"
    assert voice_session.metadata_["intent_raw"] == "Check order status"
    finding = db.scalar(select(Finding))
    assert finding is not None
    assert finding.certainty == "inferred_contributing_factor"
    evidence = list(db.scalars(select(FindingEvidence)))
    assert {item.entity_type for item in evidence} == {"event", "span", "turn"}
    assert voice_session.outcome == "success"
    assert voice_session.outcome_source == "semantic"
    assert "response_format" not in captured["json"]
    assert "success|failed|escalated|abandoned|uncertain" in captured["json"]["messages"][0][
        "content"
    ]
    prompt = captured["json"]["messages"][1]["content"]
    assert "must-not-be-sent" not in prompt
    assert "123-45-6789" not in prompt


def test_semantic_evaluator_can_use_a_separate_direct_deepseek_key(monkeypatch) -> None:
    db, voice_session, _project = database()
    settings = get_settings()
    monkeypatch.setattr(settings, "semantic_evaluator_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", "deepseek-test-key")
    monkeypatch.setattr(settings, "deepseek_model", "deepseek-flash")

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": semantic_json()}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 40},
            }

    captured = {}

    def post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("voker_voice_api.semantic.httpx.post", post)

    assert evaluate_session(db, session_id=voice_session.id) == 1
    run = db.scalar(select(AnalysisRun))
    assert run is not None
    assert run.status == "completed"
    assert run.model == "deepseek-flash"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer deepseek-test-key"
    assert captured["json"]["response_format"] == {"type": "json_object"}


def test_invalid_semantic_schema_is_retried_once_and_then_persisted(monkeypatch) -> None:
    db, voice_session, _project = database()
    settings = get_settings()
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_model", "test/model")
    contents = iter(["not valid JSON", semantic_json()])
    calls = 0

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": next(contents)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001},
            }

    def post(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return Response()

    monkeypatch.setattr("voker_voice_api.semantic.httpx.post", post)

    assert evaluate_session(db, session_id=voice_session.id) == 1
    assert calls == 2
    run = db.scalar(select(AnalysisRun))
    assert run is not None
    assert run.status == "completed"
    assert run.input_tokens == 20
    assert run.output_tokens == 10
    assert run.cost_micros == 200


def test_unknown_evidence_marks_run_insufficient_and_publishes_no_summary(
    monkeypatch,
) -> None:
    db, voice_session, _project = database()
    settings = get_settings()
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_model", "test/model")

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": semantic_json(
                                event_id="cross-session-event",
                                finding_event_id="unknown-event",
                            )
                        }
                    }
                ],
                "usage": {},
            }

    monkeypatch.setattr("voker_voice_api.semantic.httpx.post", lambda *_a, **_k: Response())

    assert evaluate_session(db, session_id=voice_session.id) == 0
    run = db.scalar(select(AnalysisRun))
    assert run is not None
    assert run.status == "insufficient_evidence"
    assert run.result is not None
    assert run.result["authoritative_summary"] is None
    assert db.scalar(select(Finding)) is None
    assert voice_session.outcome is None


def test_project_setting_persists_disabled_state_without_calling_provider(
    monkeypatch,
) -> None:
    db, voice_session, _project = database(semantic_enabled=False)
    settings = get_settings()
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_model", "test/model")
    monkeypatch.setattr(
        "voker_voice_api.semantic.httpx.post",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("provider called")),
    )

    assert evaluate_session(db, session_id=voice_session.id) == 0
    run = db.scalar(select(AnalysisRun))
    assert run is not None
    assert run.status == "disabled"
    assert run.completed_at is not None


def test_provider_failure_is_visible_and_does_not_escape_worker_boundary(
    monkeypatch,
) -> None:
    db, voice_session, _project = database()
    settings = get_settings()
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_model", "test/model")
    calls = 0

    def post(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("voker_voice_api.semantic.httpx.post", post)

    assert evaluate_session(db, session_id=voice_session.id) == 0
    run = db.scalar(select(AnalysisRun))
    assert run is not None
    assert run.status == "failed"
    assert "ConnectError" in (run.error or "")
    assert run.result is not None
    assert run.result["authoritative_summary"] is None
    assert calls == 2


def test_reanalysis_versions_and_preserves_prior_deterministic_findings() -> None:
    db, voice_session, _project = database()
    span = db.scalar(select(Span))
    assert span is not None
    span.status = "timeout"
    span.duration_ms = 6000
    span.attributes = {"retry_count": 1}

    first = run_deterministic_analysis(db, session_id=voice_session.id)
    second = run_deterministic_analysis(db, session_id=voice_session.id)

    assert first > 0
    assert second == first
    runs = list(db.scalars(select(AnalysisRun).order_by(AnalysisRun.analysis_version)))
    assert [run.analysis_version for run in runs] == [1, 2]
    assert all(run.status == "completed" for run in runs)
    assert len(list(db.scalars(select(Finding)))) == first + second
