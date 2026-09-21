from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from voker_voice_api.models import (
    Agent,
    APIKey,
    CostRecord,
    Environment,
    Error,
    Event,
    Finding,
    FindingEvidence,
    Organization,
    Project,
    Recording,
    Span,
    Turn,
    UsageRecord,
)
from voker_voice_api.models import Session as VoiceSession
from voker_voice_api.security import GeneratedAPIKey, generate_ingest_key

DEVELOPMENT_ORGANIZATION = "Voker Development"
DEVELOPMENT_PROJECT_SLUG = "voker-voice"
DEVELOPMENT_ENVIRONMENT_SLUG = "development"
DEVELOPMENT_AGENT_SLUG = "support-agent"


def ensure_development_seed(db: Session) -> tuple[Organization, Project, Environment, Agent]:
    """Create the non-secret local development ownership hierarchy idempotently."""

    organization = db.scalar(
        select(Organization).where(Organization.name == DEVELOPMENT_ORGANIZATION)
    )
    if organization is None:
        organization = Organization(name=DEVELOPMENT_ORGANIZATION)
        db.add(organization)
        db.flush()

    project = db.scalar(
        select(Project).where(
            Project.organization_id == organization.id,
            Project.slug == DEVELOPMENT_PROJECT_SLUG,
        )
    )
    if project is None:
        project = Project(
            organization_id=organization.id,
            name="Voker Voice",
            slug=DEVELOPMENT_PROJECT_SLUG,
        )
        db.add(project)
        db.flush()

    environment = db.scalar(
        select(Environment).where(
            Environment.project_id == project.id,
            Environment.slug == DEVELOPMENT_ENVIRONMENT_SLUG,
        )
    )
    if environment is None:
        environment = Environment(
            project_id=project.id,
            name="Development",
            slug=DEVELOPMENT_ENVIRONMENT_SLUG,
            kind="development",
        )
        db.add(environment)
        db.flush()

    agent = db.scalar(
        select(Agent).where(
            Agent.project_id == project.id,
            Agent.slug == DEVELOPMENT_AGENT_SLUG,
        )
    )
    if agent is None:
        agent = Agent(
            project_id=project.id,
            name="Support Agent",
            slug=DEVELOPMENT_AGENT_SLUG,
            source="custom",
        )
        db.add(agent)
        db.flush()

    return organization, project, environment, agent


def create_ingest_key(
    db: Session, *, project: Project, environment: Environment, label: str
) -> GeneratedAPIKey:
    """Create a project/environment scoped key and return its raw value once."""

    generated = generate_ingest_key("live" if environment.kind == "production" else "test")
    db.add(
        APIKey(
            project_id=project.id,
            environment_id=environment.id,
            label=label,
            prefix=generated.prefix,
            secret_hash=generated.secret_hash,
        )
    )
    db.flush()
    return generated


def seed_demo_sessions(db: Session, *, count: int = 20) -> int:
    """Create idempotent, relationally complete traces for local UI review.

    This bypasses no application tables: each demo call has persisted turns,
    events, spans, usage/cost, recordings, and evidence-linked findings.
    """

    _, project, environment, agent = ensure_development_seed(db)
    created = 0
    baseline = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=count * 2)
    audio_asset = "kave_msri-cinematic-hit-3-317170.mp3"
    for index in range(1, count + 1):
        external_id = f"demo-call-{index:03d}"
        if db.scalar(
            select(VoiceSession.id).where(
                VoiceSession.project_id == project.id,
                VoiceSession.environment_id == environment.id,
                VoiceSession.external_session_id == external_id,
            )
        ):
            continue
        started_at = baseline + timedelta(hours=index * 2)
        has_error = index % 4 == 0
        slow_stt = index % 3 == 0
        session = VoiceSession(
            project_id=project.id,
            environment_id=environment.id,
            agent_id=agent.id,
            external_session_id=external_id,
            trace_id=f"demo-trace-{index:03d}",
            source=("vapi" if index % 2 else "retell"),
            status="failed" if has_error else "completed",
            outcome="failed" if has_error else "resolved",
            outcome_source="demo_seed",
            started_at=started_at,
            ended_at=started_at + timedelta(seconds=208),
            metadata_={"seed": "demo", "scenario": "retry" if has_error else "support"},
        )
        db.add(session)
        db.flush()
        customer_turn = Turn(
            session_id=session.id,
            external_turn_id=f"demo-{index}-turn-1",
            sequence=1,
            speaker="customer",
            started_at=started_at + timedelta(seconds=4),
            ended_at=started_at + timedelta(seconds=19),
            transcript=(
                "I need help updating my subscription."
                if index % 2
                else "Can you check the status of my order?"
            ),
            attributes={"seed": "demo"},
        )
        agent_turn = Turn(
            session_id=session.id,
            external_turn_id=f"demo-{index}-turn-2",
            sequence=2,
            speaker="agent",
            started_at=started_at + timedelta(seconds=21),
            ended_at=started_at + timedelta(seconds=44),
            transcript="I can help with that. Let me review the details for you.",
            attributes={"seed": "demo"},
        )
        db.add_all((customer_turn, agent_turn))
        db.flush()
        stt_duration = 1820 if slow_stt else 420 + (index * 35)
        stt_span = Span(
            session_id=session.id,
            turn_id=customer_turn.id,
            external_span_id=f"demo-{index}-stt",
            name="speech recognition",
            kind="stt",
            status="ok",
            source="deepgram",
            started_at=customer_turn.started_at,
            ended_at=customer_turn.started_at + timedelta(milliseconds=stt_duration),
            duration_ms=stt_duration,
            attributes={"seed": "demo"},
            input_={"audio_seconds": 15},
            output={"text": customer_turn.transcript},
        )
        llm_span = Span(
            session_id=session.id,
            turn_id=agent_turn.id,
            external_span_id=f"demo-{index}-llm",
            name="support response",
            kind="llm",
            status="error" if has_error else "ok",
            source="openai",
            started_at=agent_turn.started_at,
            ended_at=agent_turn.started_at + timedelta(milliseconds=2400 + index * 25),
            duration_ms=2400 + index * 25,
            attributes={"seed": "demo"},
            input_={"text": customer_turn.transcript},
            output={"text": agent_turn.transcript},
        )
        db.add_all((stt_span, llm_span))
        db.flush()
        stt_event = Event(
            project_id=project.id,
            session_id=session.id,
            span_id=stt_span.id,
            turn_id=customer_turn.id,
            event_id=f"demo-{index}-stt-completed",
            event_type="stt.completed",
            sequence=1,
            occurred_at=stt_span.ended_at,
            status="ok",
            duration_ms=stt_duration,
            payload={"seed": "demo", "transcript": customer_turn.transcript},
            raw_payload=None,
        )
        reply_event = Event(
            project_id=project.id,
            session_id=session.id,
            span_id=llm_span.id,
            turn_id=agent_turn.id,
            event_id=f"demo-{index}-agent-reply",
            event_type="agent.reply",
            sequence=2,
            occurred_at=agent_turn.ended_at,
            status="error" if has_error else "ok",
            duration_ms=llm_span.duration_ms,
            payload={"seed": "demo", "text": agent_turn.transcript},
            raw_payload=None,
        )
        end_event = Event(
            project_id=project.id,
            session_id=session.id,
            event_id=f"demo-{index}-ended",
            event_type="session.ended",
            sequence=3,
            occurred_at=session.ended_at,
            status="error" if has_error else "ok",
            duration_ms=None,
            payload={"seed": "demo", "outcome": session.outcome},
            raw_payload=None,
        )
        db.add_all((stt_event, reply_event, end_event))
        db.flush()
        db.add(
            UsageRecord(
                session_id=session.id,
                span_id=llm_span.id,
                provider="openai",
                model="gpt-4o-mini",
                input_tokens=180 + index,
                output_tokens=95,
                total_tokens=275 + index,
                audio_seconds=15,
                tts_characters=92,
                attributes={"seed": "demo"},
            )
        )
        db.add(
            CostRecord(
                session_id=session.id,
                span_id=llm_span.id,
                currency="USD",
                amount_micros=220 + index * 8,
                source="estimate",
                rate_card_version="demo",
                is_estimate=True,
            )
        )
        db.add(
            Recording(
                session_id=session.id,
                source="local",
                external_id=f"demo-audio-{index}",
                asset_reference=audio_asset,
                duration_ms=208_000,
                media_type="audio/mpeg",
                status="available",
            )
        )
        if has_error:
            error = Error(
                session_id=session.id,
                span_id=llm_span.id,
                event_id=reply_event.id,
                type="ProviderTimeout",
                code="UPSTREAM_TIMEOUT",
                message="The provider did not return a response before the configured deadline.",
                retryable=True,
                retry_count=1,
            )
            db.add(error)
            finding = Finding(
                session_id=session.id,
                type="execution_error",
                certainty="observed",
                severity="high",
                statement="The agent response timed out before a complete answer was returned.",
                confidence=1,
                rule_id=f"demo-timeout-{index}",
                rule_version="demo",
                attributes={"seed": "demo"},
            )
            db.add(finding)
            db.flush()
            db.add(
                FindingEvidence(
                    finding_id=finding.id, entity_type="event", entity_id=reply_event.id
                )
            )
        elif slow_stt:
            finding = Finding(
                session_id=session.id,
                type="latency_threshold_exceeded",
                certainty="observed",
                severity="medium",
                statement=(
                    f"Speech recognition took {stt_duration} ms, "
                    "above the 1200 ms review threshold."
                ),
                confidence=1,
                rule_id=f"demo-slow-stt-{index}",
                rule_version="demo",
                attributes={"seed": "demo"},
            )
            db.add(finding)
            db.flush()
            db.add(
                FindingEvidence(finding_id=finding.id, entity_type="span", entity_id=stt_span.id)
            )
        created += 1
    return created
