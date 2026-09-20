"""Evidence-backed deterministic conversation analysis.

This intentionally runs without an LLM. Semantic evaluation is layered on top later;
the deterministic findings remain useful and independently verifiable.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from voker_voice_api.models import (
    AnalysisRun,
    Error,
    Event,
    Finding,
    FindingEvidence,
    Span,
)
from voker_voice_api.models import Session as VoiceSession

RULE_VERSION = "1"
LATENCY_THRESHOLDS_MS = {"stt": 1200, "llm": 3000, "tool": 5000, "tts": 2000}


@dataclass(frozen=True)
class FindingSpec:
    rule_id: str
    finding_type: str
    severity: str
    statement: str
    entity_type: str
    entity_id: uuid.UUID


def deterministic_finding_specs(errors: list[Error], spans: list[Span]) -> list[FindingSpec]:
    specs: list[FindingSpec] = []
    for error in errors:
        entity_id = error.event_id or error.span_id
        if entity_id is None:
            continue
        specs.append(
            FindingSpec(
                rule_id=f"error:{error.id}",
                finding_type="execution_error",
                severity="high",
                statement=f"{error.type} was recorded: {error.message}",
                entity_type="event" if error.event_id else "span",
                entity_id=entity_id,
            )
        )
    for span in spans:
        if span.status in {"timeout", "cancelled"}:
            specs.append(
                FindingSpec(
                    rule_id=f"terminal-span:{span.id}",
                    finding_type="timeout" if span.status == "timeout" else "cancelled_execution",
                    severity="high" if span.status == "timeout" else "medium",
                    statement=f"{span.kind} span '{span.name}' ended with status {span.status}.",
                    entity_type="span",
                    entity_id=span.id,
                )
            )
        threshold = LATENCY_THRESHOLDS_MS.get(span.kind)
        exceeds_threshold = (
            threshold is not None
            and span.duration_ms is not None
            and float(span.duration_ms) > threshold
        )
        if exceeds_threshold:
            specs.append(
                FindingSpec(
                    rule_id=f"slow-span:{span.id}",
                    finding_type="latency_threshold_exceeded",
                    severity="medium",
                    statement=(
                        f"{span.kind} span '{span.name}' took {float(span.duration_ms):.0f} ms, "
                        f"above the {threshold} ms threshold."
                    ),
                    entity_type="span",
                    entity_id=span.id,
                )
            )
    return specs


def event_finding_specs(events: list[Event]) -> list[FindingSpec]:
    """Produce bounded, evidence-linked voice-condition findings from canonical events."""

    specs: list[FindingSpec] = []
    for event_type, minimum, label in (
        ("voice.interruption", 3, "interruptions"),
        ("voice.talk_over", 2, "talk-over events"),
    ):
        matching = [event for event in events if event.event_type == event_type]
        if len(matching) >= minimum:
            evidence = matching[-1]
            specs.append(
                FindingSpec(
                    rule_id=f"{event_type}:count:{len(matching)}",
                    finding_type=event_type.removeprefix("voice."),
                    severity="medium",
                    statement=f"{len(matching)} {label} were observed (threshold: {minimum}).",
                    entity_type="event",
                    entity_id=evidence.id,
                )
            )
    return specs


def run_deterministic_analysis(db: Session, *, session_id: uuid.UUID) -> int:
    """Persist idempotent findings and link every statement to a trace entity."""

    session = db.get(VoiceSession, session_id)
    if session is None:
        return 0
    analysis_run = AnalysisRun(
        session_id=session.id,
        status="running",
        prompt_version="deterministic-v1",
    )
    db.add(analysis_run)
    db.flush()

    errors = list(db.scalars(select(Error).where(Error.session_id == session.id)))
    spans = list(db.scalars(select(Span).where(Span.session_id == session.id)))
    events = list(db.scalars(select(Event).where(Event.session_id == session.id)))
    created = 0
    for spec in [*deterministic_finding_specs(errors, spans), *event_finding_specs(events)]:
        exists = db.scalar(
            select(Finding.id).where(
                Finding.session_id == session.id,
                Finding.rule_id == spec.rule_id,
                Finding.rule_version == RULE_VERSION,
            )
        )
        if exists:
            continue
        finding = Finding(
            session_id=session.id,
            analysis_run_id=analysis_run.id,
            type=spec.finding_type,
            certainty="observed",
            severity=spec.severity,
            statement=spec.statement,
            confidence=1,
            rule_id=spec.rule_id,
            rule_version=RULE_VERSION,
            attributes={"evidence_entity_type": spec.entity_type},
        )
        db.add(finding)
        db.flush()
        db.add(
            FindingEvidence(
                finding_id=finding.id,
                entity_type=spec.entity_type,
                entity_id=spec.entity_id,
            )
        )
        created += 1
    analysis_run.status = "completed"
    analysis_run.result = {"engine": "deterministic", "findings_created": created}
    return created
