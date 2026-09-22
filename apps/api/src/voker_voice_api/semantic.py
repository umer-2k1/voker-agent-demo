"""Bounded, evidence-validating OpenRouter semantic evaluator."""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from voker_voice_api.config import get_settings
from voker_voice_api.models import (
    AnalysisRun,
    Event,
    Finding,
    FindingEvidence,
    Project,
    Span,
    Turn,
)
from voker_voice_api.models import Session as VoiceSession

PROMPT_VERSION = "semantic-v2"
SCHEMA_VERSION = "2"
MAX_EVIDENCE_ITEMS = 100
MAX_EVIDENCE_CHARS = 48_000
DEFAULT_EXCLUSIONS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "stacktrace",
    "token",
}


class EvidenceReference(BaseModel):
    entity_type: Literal["event", "span", "turn"]
    entity_id: str = Field(min_length=1, max_length=255)


class SemanticFinding(BaseModel):
    type: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1, max_length=800)
    severity: Literal["low", "medium", "high"]
    confidence: float = Field(ge=0, le=1)
    certainty: Literal["inferred_contributing_factor", "detected_condition"] = (
        "inferred_contributing_factor"
    )
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=8)
    next_step: str = Field(min_length=1, max_length=500)


class SemanticResult(BaseModel):
    intent: str = Field(min_length=1, max_length=400)
    outcome: Literal["success", "failed", "escalated", "abandoned", "uncertain"]
    outcome_source: Literal["explicit", "inferred", "unknown"]
    resolution_state: Literal["resolved", "unresolved", "escalated", "abandoned", "uncertain"]
    failure_category: str | None = Field(default=None, max_length=128)
    summary: str = Field(min_length=1, max_length=1200)
    confidence: float = Field(ge=0, le=1)
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=8)
    findings: list[SemanticFinding] = Field(max_length=8)


def parse_semantic_result(content: str) -> SemanticResult:
    """Accept common fenced JSON while retaining strict structured validation."""

    candidate = content.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        candidate = candidate.split("\n", maxsplit=1)[1].rsplit("\n", maxsplit=1)[0]
    return SemanticResult.model_validate_json(candidate)


def _next_analysis_version(db: Session, session_id: uuid.UUID) -> int:
    latest = db.scalar(
        select(func.max(AnalysisRun.analysis_version)).where(
            AnalysisRun.session_id == session_id,
            AnalysisRun.prompt_version.like("semantic-%"),
        )
    )
    return int(latest or 0) + 1


def _exclude(value: Any, exclusions: set[str], depth: int = 0) -> Any:
    if depth >= 8:
        return "[TRUNCATED:MAX_DEPTH]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in list(value.items())[:50]:
            normalized = str(key).lower().replace("-", "_")
            if normalized in exclusions:
                result[str(key)] = "[EXCLUDED]"
            else:
                result[str(key)] = _exclude(item, exclusions, depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [_exclude(item, exclusions, depth + 1) for item in value[:50]]
    if isinstance(value, str):
        return value[:2000] + ("…[TRUNCATED]" if len(value) > 2000 else "")
    return value


def _event_priority(event: Event) -> tuple[int, datetime]:
    important = event.status in {"error", "timeout", "cancelled"} or event.event_type.startswith(
        ("session.", "outcome.", "agent.handoff", "voice.", "correction.", "abandonment.")
    )
    return (0 if important else 1, event.occurred_at)


def build_evaluator_evidence(
    *,
    session: VoiceSession,
    events: list[Event],
    spans: list[Span],
    turns: list[Turn],
    exclusions: set[str],
) -> list[dict[str, Any]]:
    """Select bounded canonical evidence, never raw provider receipts."""

    evidence: list[dict[str, Any]] = []
    for event in sorted(events, key=_event_priority)[:50]:
        payload = event.payload
        evidence.append(
            {
                "entity_type": "event",
                "entity_id": event.event_id,
                "event_type": event.event_type,
                "status": event.status,
                "occurred_at": event.occurred_at.isoformat(),
                "duration_ms": float(event.duration_ms) if event.duration_ms is not None else None,
                "attributes": _exclude(payload.get("attributes", {}), exclusions),
                "error": _exclude(payload.get("error"), exclusions),
            }
        )
    for span in spans[:30]:
        evidence.append(
            {
                "entity_type": "span",
                "entity_id": span.external_span_id,
                "kind": span.kind,
                "name": span.name,
                "status": span.status,
                "duration_ms": float(span.duration_ms) if span.duration_ms is not None else None,
                "attributes": _exclude(span.attributes, exclusions),
            }
        )
    for turn in turns[:20]:
        evidence.append(
            {
                "entity_type": "turn",
                "entity_id": turn.external_turn_id,
                "sequence": turn.sequence,
                "speaker": turn.speaker,
                "transcript": _exclude(turn.transcript, exclusions),
                "started_at": turn.started_at.isoformat(),
                "ended_at": turn.ended_at.isoformat() if turn.ended_at else None,
            }
        )
    header = {
        "entity_type": "session_context",
        "entity_id": str(session.id),
        "status": session.status,
        "explicit_outcome": session.outcome,
        "outcome_source": session.outcome_source,
    }
    bounded = [header]
    for item in evidence[:MAX_EVIDENCE_ITEMS]:
        candidate = [*bounded, item]
        if len(json.dumps(candidate, default=str, separators=(",", ":"))) > MAX_EVIDENCE_CHARS:
            break
        bounded.append(item)
    return bounded


def _evidence_maps(
    events: list[Event], spans: list[Span], turns: list[Turn]
) -> dict[tuple[str, str], uuid.UUID]:
    valid: dict[tuple[str, str], uuid.UUID] = {}
    for event in events:
        valid[("event", event.event_id)] = event.id
        valid[("event", str(event.id))] = event.id
    for span in spans:
        valid[("span", span.external_span_id)] = span.id
        valid[("span", str(span.id))] = span.id
    for turn in turns:
        valid[("turn", turn.external_turn_id)] = turn.id
        valid[("turn", str(turn.id))] = turn.id
    return valid


def _resolved_refs(
    refs: list[EvidenceReference],
    valid: dict[tuple[str, str], uuid.UUID],
) -> list[tuple[str, uuid.UUID]] | None:
    resolved: list[tuple[str, uuid.UUID]] = []
    for reference in refs:
        entity_id = valid.get((reference.entity_type, reference.entity_id))
        if entity_id is None:
            return None
        resolved.append((reference.entity_type, entity_id))
    return resolved


def _cost_micros(usage: dict[str, Any]) -> int | None:
    cost = usage.get("cost")
    if not isinstance(cost, (int, float)) or cost < 0:
        return None
    return round(float(cost) * 1_000_000)


def evaluate_session(
    db: Session,
    *,
    session_id: uuid.UUID,
    analysis_run_id: uuid.UUID | None = None,
) -> int:
    """Run semantic analysis while preserving visible terminal states on every path."""

    settings = get_settings()
    session = db.get(VoiceSession, session_id)
    if session is None:
        return 0
    project = db.get(Project, session.project_id)
    configured = bool(settings.openrouter_api_key and settings.openrouter_model)
    project_enabled = project is None or project.semantic_analysis_enabled
    enabled = configured and project_enabled
    now = datetime.now(UTC)
    analysis_run = db.get(AnalysisRun, analysis_run_id) if analysis_run_id else None
    if analysis_run is None or analysis_run.session_id != session.id:
        analysis_run = AnalysisRun(
            session_id=session.id,
            status="running" if enabled else "disabled",
            analysis_version=_next_analysis_version(db, session.id),
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            model=settings.openrouter_model,
            started_at=now if enabled else None,
            completed_at=None if enabled else now,
        )
        db.add(analysis_run)
    else:
        analysis_run.status = "running" if enabled else "disabled"
        analysis_run.model = settings.openrouter_model
        analysis_run.started_at = now if enabled else None
        analysis_run.completed_at = None if enabled else now
    db.flush()
    if not enabled:
        reason = (
            "Semantic analysis is disabled for this project"
            if not project_enabled
            else "OpenRouter evaluator is not configured"
        )
        analysis_run.result = {"reason": reason, "authoritative_summary": None}
        return 0

    events = list(
        db.scalars(
            select(Event)
            .where(Event.session_id == session.id)
            .order_by(Event.occurred_at, Event.id)
        )
    )
    spans = list(
        db.scalars(
            select(Span).where(Span.session_id == session.id).order_by(Span.started_at, Span.id)
        )
    )
    turns = list(
        db.scalars(
            select(Turn).where(Turn.session_id == session.id).order_by(Turn.sequence, Turn.id)
        )
    )
    if not events and not spans and not turns:
        analysis_run.status = "insufficient_evidence"
        analysis_run.completed_at = datetime.now(UTC)
        analysis_run.result = {
            "reason": "No canonical events, spans, or turns were available",
            "authoritative_summary": None,
        }
        return 0

    exclusions = DEFAULT_EXCLUSIONS | {
        item.lower().replace("-", "_")
        for item in (project.semantic_content_exclusions if project else [])
        if isinstance(item, str)
    }
    evidence = build_evaluator_evidence(
        session=session,
        events=events,
        spans=spans,
        turns=turns,
        exclusions=exclusions,
    )
    encoded_evidence = json.dumps(evidence, default=str, separators=(",", ":"))
    started = time.monotonic()
    try:
        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={
                "model": settings.openrouter_model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Analyze only supplied evidence. Return JSON matching semantic schema "
                            "v2: intent, outcome, outcome_source, resolution_state, "
                            "failure_category, summary, confidence, evidence, and findings. "
                            "Evidence entries use entity_type event|span|turn and supplied "
                            "entity_id. Each finding includes type, statement, severity, "
                            "confidence, certainty, evidence, and next_step. Use "
                            "'inferred_contributing_factor' for interpretations. Never claim "
                            "causation; say associated with or observed signal."
                        ),
                    },
                    {"role": "user", "content": encoded_evidence},
                ],
            },
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()
        result = parse_semantic_result(body["choices"][0]["message"]["content"])
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        analysis_run.input_tokens = usage.get("prompt_tokens")
        analysis_run.output_tokens = usage.get("completion_tokens")
        analysis_run.cost_micros = _cost_micros(usage)
        analysis_run.evaluator_latency_ms = (time.monotonic() - started) * 1000
        valid = _evidence_maps(events, spans, turns)
        result_evidence = _resolved_refs(result.evidence, valid)
        valid_findings: list[tuple[SemanticFinding, list[tuple[str, uuid.UUID]]]] = []
        invalid_findings = 0
        for candidate in result.findings:
            resolved = _resolved_refs(candidate.evidence, valid)
            if resolved is None:
                invalid_findings += 1
                continue
            valid_findings.append((candidate, resolved))
        if result_evidence is None or (result.findings and not valid_findings):
            analysis_run.status = "insufficient_evidence"
            analysis_run.completed_at = datetime.now(UTC)
            analysis_run.result = {
                "reason": "Evaluator referenced unknown or cross-session evidence",
                "invalid_findings": invalid_findings,
                "authoritative_summary": None,
            }
            return 0

        for candidate, resolved in valid_findings:
            finding = Finding(
                session_id=session.id,
                analysis_run_id=analysis_run.id,
                type=candidate.type,
                certainty=candidate.certainty,
                severity=candidate.severity,
                statement=candidate.statement,
                confidence=candidate.confidence,
                rule_id=PROMPT_VERSION,
                rule_version=SCHEMA_VERSION,
                attributes={
                    "outcome": result.outcome,
                    "outcome_source": result.outcome_source,
                    "resolution_state": result.resolution_state,
                    "failure_category": result.failure_category,
                    "next_step": candidate.next_step,
                },
            )
            db.add(finding)
            db.flush()
            for entity_type, entity_id in resolved:
                db.add(
                    FindingEvidence(
                        finding_id=finding.id,
                        entity_type=entity_type,
                        entity_id=entity_id,
                    )
                )
        if session.outcome is None and result.outcome != "uncertain":
            session.outcome = result.outcome
            session.outcome_source = "semantic"
        analysis_run.status = "completed"
        analysis_run.completed_at = datetime.now(UTC)
        analysis_run.result = {
            "intent": result.intent,
            "outcome": result.outcome,
            "outcome_source": result.outcome_source,
            "resolution_state": result.resolution_state,
            "failure_category": result.failure_category,
            "summary": result.summary,
            "confidence": result.confidence,
            "summary_evidence": [
                {"entity_type": kind, "entity_id": str(entity_id)}
                for kind, entity_id in result_evidence
            ],
            "findings_created": len(valid_findings),
            "invalid_findings": invalid_findings,
        }
        return len(valid_findings)
    except Exception as error:
        analysis_run.status = "failed"
        analysis_run.error = f"{type(error).__name__}: {error}"[:5000]
        analysis_run.evaluator_latency_ms = (time.monotonic() - started) * 1000
        analysis_run.completed_at = datetime.now(UTC)
        analysis_run.result = {
            "reason": "Semantic evaluator failed",
            "authoritative_summary": None,
        }
        return 0
