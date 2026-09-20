from types import SimpleNamespace
from uuid import uuid4

from voker_voice_api.analysis import deterministic_finding_specs, event_finding_specs


def test_deterministic_analysis_reports_slow_span_with_span_evidence() -> None:
    span = SimpleNamespace(
        id=uuid4(), status="ok", kind="llm", name="llm.completed", duration_ms=3001
    )

    findings = deterministic_finding_specs([], [span])

    assert findings[0].finding_type == "latency_threshold_exceeded"
    assert findings[0].entity_type == "span"
    assert findings[0].entity_id == span.id


def test_deterministic_analysis_reports_repeated_interruptions() -> None:
    events = [SimpleNamespace(id=uuid4(), event_type="voice.interruption") for _ in range(3)]

    findings = event_finding_specs(events)

    assert findings[0].finding_type == "interruption"
    assert findings[0].entity_id == events[-1].id
