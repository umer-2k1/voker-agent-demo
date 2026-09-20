"""Bounded OpenRouter semantic evaluator; it never invents trace evidence."""

import uuid
from typing import Literal

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from voker_voice_api.config import get_settings
from voker_voice_api.models import Event, Finding, FindingEvidence
from voker_voice_api.models import Session as VoiceSession


class SemanticFinding(BaseModel):
    statement: str = Field(min_length=1, max_length=800)
    severity: Literal["low", "medium", "high"]
    confidence: float = Field(ge=0, le=1)
    evidence_event_ids: list[str] = Field(min_length=1, max_length=5)


class SemanticResult(BaseModel):
    outcome: Literal["success", "failed", "escalated", "abandoned", "uncertain"]
    summary: str = Field(min_length=1, max_length=1200)
    findings: list[SemanticFinding] = Field(max_length=5)


def evaluate_session(db: Session, *, session_id: uuid.UUID) -> int:
    settings = get_settings()
    if not settings.openrouter_api_key or not settings.openrouter_model:
        return 0
    session = db.get(VoiceSession, session_id)
    if session is None:
        return 0
    events = list(
        db.scalars(select(Event).where(Event.session_id == session.id).order_by(Event.occurred_at))
    )
    evidence = [
        {
            "event_id": item.event_id,
            "type": item.event_type,
            "status": item.status,
            "payload": item.payload,
        }
        for item in events
    ]
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
                        "Return JSON with outcome, summary, findings. Every finding must cite only "
                        "supplied event IDs. Do not claim causation."
                    ),
                },
                {"role": "user", "content": str(evidence)[:60000]},
            ],
        },
        timeout=30,
    )
    response.raise_for_status()
    result = SemanticResult.model_validate_json(response.json()["choices"][0]["message"]["content"])
    valid = {item.event_id: item.id for item in events}
    created = 0
    for candidate in result.findings:
        if not set(candidate.evidence_event_ids).issubset(valid):
            continue
        finding = Finding(
            session_id=session.id,
            type="semantic_failure_analysis",
            certainty="inferred",
            severity=candidate.severity,
            statement=candidate.statement,
            confidence=candidate.confidence,
            rule_id="semantic-v1",
            rule_version="1",
            attributes={"outcome": result.outcome, "summary": result.summary},
        )
        db.add(finding)
        db.flush()
        for event_id in candidate.evidence_event_ids:
            db.add(
                FindingEvidence(
                    finding_id=finding.id, entity_type="event", entity_id=valid[event_id]
                )
            )
        created += 1
    return created
