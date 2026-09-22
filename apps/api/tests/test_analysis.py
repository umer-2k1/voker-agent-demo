from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from voker_voice_api.analysis import deterministic_finding_specs, event_finding_specs


def test_deterministic_analysis_reports_slow_llm_ttft_with_span_evidence() -> None:
    span = SimpleNamespace(
        id=uuid4(),
        status="ok",
        kind="llm",
        name="model request",
        duration_ms=3001,
        ended_at=datetime.now(UTC),
        attributes={"ttft_ms": 1600},
    )

    findings = deterministic_finding_specs([], [span])

    finding = next(item for item in findings if item.finding_type == "latency_threshold_exceeded")
    assert finding.entity_type == "span"
    assert finding.entity_id == span.id
    assert finding.attributes["observed_value"] == 1600
    assert finding.attributes["threshold"] == 1500


def test_deterministic_analysis_reports_tool_failure_retry_and_timeout() -> None:
    span = SimpleNamespace(
        id=uuid4(),
        status="timeout",
        kind="tool",
        name="lookup_order",
        duration_ms=6000,
        ended_at=datetime.now(UTC),
        attributes={"retry_count": 2},
    )

    findings = deterministic_finding_specs([], [span])

    assert {item.finding_type for item in findings} == {
        "tool_retry",
        "timeout",
        "latency_threshold_exceeded",
    }
    assert all(item.certainty == "detected_condition" for item in findings)


def test_deterministic_analysis_reports_observed_voice_conditions() -> None:
    events = [
        SimpleNamespace(
            id=uuid4(),
            event_type="voice.interruption",
            status="ok",
            payload={"attributes": {}},
            turn_id=None,
            occurred_at=datetime.now(UTC),
        )
    ]

    findings = event_finding_specs(events)

    assert findings[0].finding_type == "interruption"
    assert findings[0].entity_id == events[-1].id
    assert findings[0].attributes["observed_value"] == 1


def test_response_gap_uses_both_exact_event_evidence_rows() -> None:
    turn_id = uuid4()
    stopped = SimpleNamespace(
        id=uuid4(),
        event_type="speech.stopped",
        status="ok",
        payload={"attributes": {}},
        turn_id=turn_id,
        occurred_at=datetime(2026, 9, 21, tzinfo=UTC),
    )
    playback = SimpleNamespace(
        id=uuid4(),
        event_type="playback.started",
        status="unset",
        payload={"attributes": {}},
        turn_id=turn_id,
        occurred_at=stopped.occurred_at + timedelta(seconds=3),
    )

    findings = event_finding_specs([stopped, playback])

    gap = next(item for item in findings if item.finding_type == "dead_air")
    assert gap.attributes["observed_value"] == 3000
    assert {item.entity_id for item in gap.evidence} == {stopped.id, playback.id}


def test_handoff_without_destination_run_is_detected() -> None:
    handoff = SimpleNamespace(
        id=uuid4(),
        event_type="agent.handoff",
        status="ok",
        payload={"attributes": {"from_agent": "triage", "to_agent": "billing"}},
        turn_id=None,
        occurred_at=datetime.now(UTC),
    )

    findings = event_finding_specs([handoff])

    assert findings[0].finding_type == "failed_handoff"
    assert "no destination agent run" in findings[0].statement
