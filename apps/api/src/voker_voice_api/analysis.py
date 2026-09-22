"""Evidence-backed deterministic conversation analysis."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from voker_voice_api.models import (
    AgentRun,
    AnalysisRun,
    Error,
    Event,
    Finding,
    FindingEvidence,
    Span,
    Turn,
)
from voker_voice_api.models import Session as VoiceSession

RULE_VERSION = "2"
LATENCY_THRESHOLDS_MS = {
    "stt_finalization": 1200.0,
    "llm_ttft": 1500.0,
    "tool_duration": 5000.0,
    "tts_first_audio": 1200.0,
    "response_gap": 2500.0,
}


@dataclass(frozen=True)
class EvidenceRef:
    entity_type: str
    entity_id: uuid.UUID


@dataclass(frozen=True)
class FindingSpec:
    rule_id: str
    finding_type: str
    severity: str
    statement: str
    entity_type: str
    entity_id: uuid.UUID
    certainty: str = "detected_condition"
    evidence: tuple[EvidenceRef, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)

    def evidence_refs(self) -> tuple[EvidenceRef, ...]:
        return self.evidence or (EvidenceRef(self.entity_type, self.entity_id),)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _condition(
    *,
    rule_id: str,
    finding_type: str,
    severity: str,
    statement: str,
    entity_type: str,
    entity_id: uuid.UUID,
    observed_value: Any,
    threshold: Any = None,
    certainty: str = "detected_condition",
    evidence: tuple[EvidenceRef, ...] = (),
) -> FindingSpec:
    attributes = {
        "observed_value": observed_value,
        "threshold": threshold,
        "rule_version": RULE_VERSION,
        "next_step": _next_step(finding_type),
    }
    return FindingSpec(
        rule_id=rule_id,
        finding_type=finding_type,
        severity=severity,
        statement=statement,
        entity_type=entity_type,
        entity_id=entity_id,
        certainty=certainty,
        evidence=evidence,
        attributes=attributes,
    )


def _next_step(finding_type: str) -> str:
    guidance = {
        "execution_error": "Inspect the linked error event and its provider request ID.",
        "tool_failure": "Inspect the linked tool span arguments, result, and retry path.",
        "tool_retry": "Inspect the preceding tool failure and retry attempt.",
        "timeout": "Inspect the linked stage timing and provider timeout configuration.",
        "cancelled_execution": "Inspect the linked span and surrounding interruption events.",
        "incomplete_session": "Inspect the final emitted event and application shutdown path.",
        "missing_expected_stage": "Inspect instrumentation around the missing configured stage.",
        "latency_threshold_exceeded": "Inspect the linked stage and its provider timing fields.",
        "response_gap": "Compare user speech end, generation, TTS, and playback timestamps.",
        "interruption": "Inspect playback and caller speech events around the linked evidence.",
        "talk_over": "Inspect overlapping speech timing around the linked evidence.",
        "dead_air": "Inspect stage timing between user speech and agent playback.",
        "correction": "Inspect the linked turn and preceding assistant response.",
        "abandoned_turn": "Inspect the linked turn and its terminal session events.",
        "failed_handoff": "Inspect the handoff event and expected destination agent run.",
    }
    return guidance.get(finding_type, "Inspect the linked trace evidence.")


def deterministic_finding_specs(errors: list[Error], spans: list[Span]) -> list[FindingSpec]:
    """Return execution and stage findings with exact event/span evidence."""

    specs: list[FindingSpec] = []
    for error in errors:
        entity_id = error.event_id or error.span_id
        if entity_id is None:
            continue
        specs.append(
            _condition(
                rule_id=f"recorded-error:{error.id}",
                finding_type="execution_error",
                severity="high",
                statement=f"Confirmed execution fact: {error.type} was recorded: {error.message}",
                entity_type="event" if error.event_id else "span",
                entity_id=entity_id,
                observed_value=error.type,
                certainty="confirmed_execution_fact",
            )
        )
    for span in spans:
        if span.kind == "tool" and span.status == "error":
            specs.append(
                _condition(
                    rule_id=f"tool-failure:{span.id}",
                    finding_type="tool_failure",
                    severity="high",
                    statement=f"Detected condition: tool span '{span.name}' failed.",
                    entity_type="span",
                    entity_id=span.id,
                    observed_value=span.status,
                    threshold="ok",
                )
            )
        retry_count = _number(span.attributes.get("retry_count"))
        if span.kind == "tool" and retry_count is not None and retry_count > 0:
            specs.append(
                _condition(
                    rule_id=f"tool-retry:{span.id}",
                    finding_type="tool_retry",
                    severity="medium",
                    statement=(
                        f"Detected condition: tool span '{span.name}' reported "
                        f"{int(retry_count)} retry attempt(s)."
                    ),
                    entity_type="span",
                    entity_id=span.id,
                    observed_value=int(retry_count),
                    threshold=1,
                )
            )
        if span.status in {"timeout", "cancelled"}:
            finding_type = "timeout" if span.status == "timeout" else "cancelled_execution"
            specs.append(
                _condition(
                    rule_id=f"terminal-span:{span.id}",
                    finding_type=finding_type,
                    severity="high" if span.status == "timeout" else "medium",
                    statement=(
                        f"Detected condition: {span.kind} span '{span.name}' "
                        f"ended with status {span.status}."
                    ),
                    entity_type="span",
                    entity_id=span.id,
                    observed_value=span.status,
                    threshold="ok",
                )
            )
        if span.status == "unset" and span.ended_at is None:
            specs.append(
                _condition(
                    rule_id=f"unfinished-span:{span.id}",
                    finding_type="incomplete_stage",
                    severity="medium",
                    statement=f"Detected condition: {span.kind} span '{span.name}' did not finish.",
                    entity_type="span",
                    entity_id=span.id,
                    observed_value="unset",
                    threshold="terminal status",
                )
            )
        _append_latency_findings(specs, span)
    return specs


def _append_latency_findings(specs: list[FindingSpec], span: Span) -> None:
    checks: list[tuple[str, float | None, float, str]] = []
    duration = _number(span.duration_ms)
    if span.kind == "stt":
        checks.append(
            (
                "stt_finalization",
                duration,
                LATENCY_THRESHOLDS_MS["stt_finalization"],
                "STT finalization",
            )
        )
    elif span.kind == "tool":
        checks.append(
            (
                "tool_duration",
                duration,
                LATENCY_THRESHOLDS_MS["tool_duration"],
                "Tool execution",
            )
        )
    elif span.kind == "llm":
        checks.append(
            (
                "llm_ttft",
                _number(span.attributes.get("ttft_ms")),
                LATENCY_THRESHOLDS_MS["llm_ttft"],
                "LLM time to first token",
            )
        )
    elif span.kind == "tts":
        checks.append(
            (
                "tts_first_audio",
                _number(span.attributes.get("ttfb_ms") or span.attributes.get("first_audio_ms")),
                LATENCY_THRESHOLDS_MS["tts_first_audio"],
                "TTS time to first audio",
            )
        )
    for metric, observed, threshold, label in checks:
        if observed is None or observed <= threshold:
            continue
        specs.append(
            _condition(
                rule_id=f"latency:{metric}:{span.id}",
                finding_type="latency_threshold_exceeded",
                severity="medium",
                statement=(
                    f"Detected condition: {label} was {observed:.0f} ms, "
                    f"above the {threshold:.0f} ms threshold."
                ),
                entity_type="span",
                entity_id=span.id,
                observed_value=observed,
                threshold=threshold,
            )
        )


def event_finding_specs(events: list[Event]) -> list[FindingSpec]:
    """Return observed voice behavior, retry, and response-gap findings."""

    specs: list[FindingSpec] = []
    grouped: dict[str, list[Event]] = {}
    for event in events:
        grouped.setdefault(event.event_type, []).append(event)
    for event_type, finding_type, label in (
        ("voice.interruption", "interruption", "caller interruption"),
        ("voice.talk_over", "talk_over", "talk-over"),
        ("correction.detected", "correction", "caller correction"),
        ("abandonment.detected", "abandoned_turn", "abandonment"),
    ):
        matching = grouped.get(event_type, [])
        if not matching:
            continue
        evidence = matching[-1]
        specs.append(
            _condition(
                rule_id=f"voice-condition:{event_type}:{evidence.id}",
                finding_type=finding_type,
                severity="medium",
                statement=(
                    f"Detected condition: {len(matching)} {label} "
                    f"observation{'s' if len(matching) != 1 else ''} occurred."
                ),
                entity_type="event",
                entity_id=evidence.id,
                observed_value=len(matching),
                threshold=1,
                evidence=tuple(EvidenceRef("event", item.id) for item in matching[-10:]),
            )
        )
    for retry in grouped.get("graph.retry", []):
        specs.append(
            _condition(
                rule_id=f"graph-retry:{retry.id}",
                finding_type="tool_retry",
                severity="medium",
                statement="Detected condition: a graph or provider operation was retried.",
                entity_type="event",
                entity_id=retry.id,
                observed_value=retry.payload.get("attributes", {}).get("attempt"),
                threshold=1,
            )
        )
    specs.extend(_response_gap_specs(events))
    specs.extend(_handoff_specs(events))
    return specs


def _response_gap_specs(events: list[Event]) -> list[FindingSpec]:
    specs: list[FindingSpec] = []
    stopped_by_turn: dict[uuid.UUID, Event] = {}
    for event in events:
        if event.turn_id is None:
            continue
        if event.event_type == "speech.stopped":
            stopped_by_turn[event.turn_id] = event
        elif event.event_type == "playback.started" and event.turn_id in stopped_by_turn:
            stopped = stopped_by_turn[event.turn_id]
            observed = max(0.0, (event.occurred_at - stopped.occurred_at).total_seconds() * 1000)
            threshold = LATENCY_THRESHOLDS_MS["response_gap"]
            if observed <= threshold:
                continue
            specs.append(
                _condition(
                    rule_id=f"response-gap:{event.turn_id}:{event.id}",
                    finding_type="dead_air",
                    severity="medium",
                    statement=(
                        f"Detected condition: the response gap was {observed:.0f} ms, "
                        f"above the {threshold:.0f} ms threshold."
                    ),
                    entity_type="event",
                    entity_id=event.id,
                    observed_value=observed,
                    threshold=threshold,
                    evidence=(
                        EvidenceRef("event", stopped.id),
                        EvidenceRef("event", event.id),
                    ),
                )
            )
    return specs


def _handoff_specs(events: list[Event]) -> list[FindingSpec]:
    specs: list[FindingSpec] = []
    starts = [
        event for event in events if event.event_type == "agent.started" and event.status != "error"
    ]
    for handoff in (event for event in events if event.event_type == "agent.handoff"):
        attributes = handoff.payload.get("attributes", {})
        destination = attributes.get("to_agent")
        has_destination = any(
            item.occurred_at >= handoff.occurred_at
            and item.payload.get("agent", {}).get("name") == destination
            for item in starts
        )
        if handoff.status != "error" and destination and has_destination:
            continue
        specs.append(
            _condition(
                rule_id=f"failed-handoff:{handoff.id}",
                finding_type="failed_handoff",
                severity="high",
                statement=(
                    "Detected condition: the handoff failed or no destination "
                    "agent run was observed."
                ),
                entity_type="event",
                entity_id=handoff.id,
                observed_value=destination or "missing destination",
                threshold="destination agent.started",
            )
        )
    return specs


def _session_finding_specs(
    session: VoiceSession,
    events: list[Event],
    spans: list[Span],
    turns: list[Turn],
    agent_runs: list[AgentRun],
) -> list[FindingSpec]:
    del agent_runs
    specs: list[FindingSpec] = []
    terminal_event = next(
        (
            event
            for event in reversed(events)
            if event.event_type in {"session.ended", "session.error"}
        ),
        events[-1] if events else None,
    )
    if session.status in {"in_progress", "incomplete"} and terminal_event is not None:
        specs.append(
            _condition(
                rule_id=f"incomplete-session:{session.id}",
                finding_type="incomplete_session",
                severity="high",
                statement=(
                    f"Detected condition: the session remained {session.status} "
                    "instead of completing."
                ),
                entity_type="event",
                entity_id=terminal_event.id,
                observed_value=session.status,
                threshold="completed",
            )
        )
    expected = session.metadata_.get("expected_stages", [])
    observed_kinds = {span.kind for span in spans}
    if isinstance(expected, list) and terminal_event is not None:
        for stage in expected:
            if not isinstance(stage, str) or stage in observed_kinds:
                continue
            specs.append(
                _condition(
                    rule_id=f"missing-stage:{session.id}:{stage}",
                    finding_type="missing_expected_stage",
                    severity="medium",
                    statement=(f"Detected condition: configured stage '{stage}' was not observed."),
                    entity_type="event",
                    entity_id=terminal_event.id,
                    observed_value=False,
                    threshold=f"{stage} span present",
                )
            )
    for turn in turns:
        if turn.ended_at is None or turn.attributes.get("abandoned") is True:
            specs.append(
                _condition(
                    rule_id=f"abandoned-turn:{turn.id}",
                    finding_type="abandoned_turn",
                    severity="medium",
                    statement=f"Detected condition: turn {turn.sequence} was abandoned.",
                    entity_type="turn",
                    entity_id=turn.id,
                    observed_value="abandoned",
                    threshold="completed",
                )
            )
    return specs


def _next_analysis_version(db: Session, session_id: uuid.UUID) -> int:
    latest = db.scalar(
        select(func.max(AnalysisRun.analysis_version)).where(
            AnalysisRun.session_id == session_id,
            AnalysisRun.prompt_version.like("deterministic-%"),
        )
    )
    return int(latest or 0) + 1


def run_deterministic_analysis(
    db: Session,
    *,
    session_id: uuid.UUID,
    analysis_run_id: uuid.UUID | None = None,
) -> int:
    """Persist immutable findings and link every claim to same-session evidence."""

    session = db.get(VoiceSession, session_id)
    if session is None:
        return 0
    now = datetime.now(UTC)
    analysis_run = db.get(AnalysisRun, analysis_run_id) if analysis_run_id else None
    if analysis_run is None or analysis_run.session_id != session.id:
        analysis_run = AnalysisRun(
            session_id=session.id,
            status="running",
            analysis_version=_next_analysis_version(db, session.id),
            prompt_version="deterministic-v2",
            schema_version="2",
            started_at=now,
        )
        db.add(analysis_run)
    else:
        analysis_run.status = "running"
        analysis_run.started_at = now
    db.flush()

    errors = list(db.scalars(select(Error).where(Error.session_id == session.id)))
    spans = list(db.scalars(select(Span).where(Span.session_id == session.id)))
    events = list(
        db.scalars(
            select(Event)
            .where(Event.session_id == session.id)
            .order_by(Event.occurred_at, Event.id)
        )
    )
    turns = list(db.scalars(select(Turn).where(Turn.session_id == session.id)))
    agent_runs = list(db.scalars(select(AgentRun).where(AgentRun.session_id == session.id)))
    specs = [
        *deterministic_finding_specs(errors, spans),
        *event_finding_specs(events),
        *_session_finding_specs(session, events, spans, turns, agent_runs),
    ]
    for spec in specs:
        finding = Finding(
            session_id=session.id,
            analysis_run_id=analysis_run.id,
            type=spec.finding_type,
            certainty=spec.certainty,
            severity=spec.severity,
            statement=spec.statement,
            confidence=1,
            rule_id=spec.rule_id,
            rule_version=RULE_VERSION,
            attributes={
                **spec.attributes,
                "evidence_entity_type": spec.entity_type,
                "evidence_ids": [
                    {"entity_type": item.entity_type, "entity_id": str(item.entity_id)}
                    for item in spec.evidence_refs()
                ],
            },
        )
        db.add(finding)
        db.flush()
        for evidence in spec.evidence_refs():
            db.add(
                FindingEvidence(
                    finding_id=finding.id,
                    entity_type=evidence.entity_type,
                    entity_id=evidence.entity_id,
                )
            )
    analysis_run.status = "completed"
    analysis_run.completed_at = datetime.now(UTC)
    analysis_run.result = {
        "engine": "deterministic",
        "certainty": "detected_condition",
        "findings_created": len(specs),
        "rule_version": RULE_VERSION,
    }
    return len(specs)
