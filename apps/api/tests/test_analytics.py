from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from voker_voice_api.analytics import CohortValue, latency_distribution, voice_impact_cohorts
from voker_voice_api.database import Base
from voker_voice_api.models import (
    Agent,
    AgentVersion,
    CostRecord,
    Environment,
    Error,
    Event,
    Finding,
    Organization,
    OrganizationMember,
    Project,
    Span,
    UsageRecord,
    User,
)
from voker_voice_api.models import Session as VoiceSession
from voker_voice_api.routers.dashboard import analytics_overview


def test_voice_impact_omits_small_cohorts() -> None:
    values = [CohortValue(str(index), "success", 3, 1500) for index in range(4)]

    cohorts = voice_impact_cohorts(values)

    assert cohorts["high_interruption"] is None
    assert cohorts["slow_stt"] is None
    assert cohorts["dead_air"] is None


def test_voice_impact_reports_only_observed_outcomes() -> None:
    values = [
        CohortValue(str(index), "success" if index < 3 else "failed", 3, 1500) for index in range(5)
    ]
    values.append(CohortValue("unknown", None, 3, 1500))

    cohort = voice_impact_cohorts(values)["high_interruption"]

    assert cohort == {"sample_size": 5, "resolved": 3, "resolution_rate": 0.6}


def test_voice_impact_reports_dead_air_only_with_observed_outcomes() -> None:
    values = [CohortValue(str(index), "resolved", 0, 300, 1) for index in range(5)]
    values.append(CohortValue("unknown", None, 0, 300, 1))

    cohort = voice_impact_cohorts(values)["dead_air"]

    assert cohort == {"sample_size": 5, "resolved": 5, "resolution_rate": 1}


def test_latency_distribution_reports_observed_percentiles() -> None:
    distribution = latency_distribution([10, 20, 30, 40, 50, 60])

    assert distribution == {
        "sample_size": 6,
        "p50_ms": 30,
        "p90_ms": 50,
        "p95_ms": 60,
        "max_ms": 60,
    }


def test_latency_distribution_keeps_missing_data_unknown() -> None:
    assert latency_distribution([]) is None


def test_analytics_uses_filtered_aggregates_and_links_representative_sessions() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    organization = Organization(name="Analytics")
    db.add(organization)
    db.flush()
    user = User(email="analytics@example.test")
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
    development = Environment(
        project_id=project.id, name="Development", slug="development", kind="development"
    )
    production = Environment(
        project_id=project.id, name="Production", slug="production", kind="production"
    )
    agent = Agent(project_id=project.id, name="Support", slug="support", source="vapi")
    db.add_all([development, production, agent])
    db.flush()
    version = AgentVersion(agent_id=agent.id, version="3", metadata_={})
    db.add(version)
    db.flush()
    started_at = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)

    sessions: list[VoiceSession] = []
    for index in range(6):
        session = VoiceSession(
            project_id=project.id,
            environment_id=development.id,
            agent_id=agent.id,
            agent_version_id=version.id,
            external_session_id=f"call-{index}",
            trace_id=f"trace-{index}",
            source="vapi" if index < 3 else "sdk",
            status="completed",
            outcome="resolved" if index < 4 else "failed",
            outcome_source="explicit" if index < 3 else "semantic",
            started_at=started_at + timedelta(minutes=index),
            ended_at=started_at + timedelta(minutes=index, seconds=30),
            metadata_={},
        )
        db.add(session)
        db.flush()
        sessions.append(session)
        for interruption in range(3):
            db.add(
                Event(
                    project_id=project.id,
                    session_id=session.id,
                    event_id=f"interrupt-{index}-{interruption}",
                    event_type="voice.interruption",
                    occurred_at=session.started_at,
                    status="ok",
                    payload={},
                )
            )
        db.add_all(
            [
                Event(
                    project_id=project.id,
                    session_id=session.id,
                    event_id=f"stt-{index}",
                    event_type="stt.completed",
                    occurred_at=session.started_at,
                    status="ok",
                    duration_ms=1500,
                    payload={},
                ),
                Event(
                    project_id=project.id,
                    session_id=session.id,
                    event_id=f"dead-air-{index}",
                    event_type="voice.dead_air",
                    occurred_at=session.started_at,
                    status="ok",
                    payload={},
                ),
                Span(
                    session_id=session.id,
                    external_span_id=f"llm-{index}",
                    name="llm",
                    kind="llm",
                    status="ok",
                    started_at=session.started_at,
                    duration_ms=250 + index,
                    attributes={},
                ),
                Span(
                    session_id=session.id,
                    external_span_id=f"stt-span-{index}",
                    name="stt",
                    kind="stt",
                    status="ok",
                    started_at=session.started_at,
                    duration_ms=400 + index,
                    attributes={},
                ),
                UsageRecord(
                    session_id=session.id,
                    provider="openai",
                    model="gpt-4o-mini",
                    input_tokens=10,
                    output_tokens=5,
                    total_tokens=15,
                    audio_seconds=2.5,
                    tts_characters=50,
                    attributes={},
                ),
                CostRecord(
                    session_id=session.id,
                    amount_micros=0 if index == 0 else 100,
                    source="provider" if index < 3 else "estimate",
                    rate_card_version=None if index < 3 else "openai-2026-09",
                    is_estimate=index >= 3,
                ),
            ]
        )

    db.add_all(
        [
            Error(session_id=sessions[4].id, type="ToolError", message="lookup failed"),
            Span(
                session_id=sessions[4].id,
                external_span_id="tool-failed",
                name="lookup",
                kind="tool",
                status="error",
                started_at=sessions[4].started_at,
                duration_ms=40,
                attributes={},
            ),
            Finding(
                session_id=sessions[4].id,
                type="tool_failure",
                certainty="confirmed",
                statement="A tool failed.",
                attributes={"failure_category": "tool_failure"},
            ),
            VoiceSession(
                project_id=project.id,
                environment_id=production.id,
                external_session_id="production-call",
                trace_id="production-trace",
                source="retell",
                status="completed",
                outcome="resolved",
                outcome_source="provider",
                started_at=started_at,
                metadata_={},
            ),
        ]
    )
    db.commit()

    result = analytics_overview("voice", user, environment="development", db=db)

    assert result["session_count"] == 6
    assert result["completed_session_count"] == 6
    assert result["rates"]["resolution"] == 4 / 6
    assert result["cost"]["record_count"] == 6
    assert result["cost"]["exact_record_count"] == 3
    assert result["cost"]["estimated_record_count"] == 3
    assert result["cost"]["amount_micros"] == 500
    assert result["usage"]["audio_seconds"] == 15
    assert result["usage"]["tts_characters"] == 300
    assert result["voice_impact_cohorts"]["high_interruption"]["sample_size"] == 6
    assert len(result["voice_impact_cohorts"]["dead_air"]["session_ids"]) == 6
    assert result["latency"]["llm"]["sample_size"] == 6
    assert result["latency"]["llm"]["p90_ms"] == 254
    assert result["voice_impact_cohorts"]["fast_stt"]["sample_size"] == 6
    assert result["volume_trend"] == [{"date": "2026-09-21", "sessions": 6}]
    assert result["rates_trend"][0]["date"] == "2026-09-21"
    assert result["rates_trend"][0]["sessions"] == 6
    assert result["rates_trend"][0]["known_outcomes"] == 6
    assert result["rates_trend"][0]["resolution_rate"] == 4 / 6
    assert "correction_rate" in result["rates_trend"][0]
    assert result["intent_comparisons"][0]["label"] == "Unknown intent"
    assert result["intent_comparisons"][0]["resolution_rate"] == 4 / 6
    assert len(result["interruption_resolution_points"]) == 6
    assert result["interruption_resolution_points"][0]["session_id"] == str(sessions[0].id)
    assert result["tool_failure_count"] == 1
    assert result["insights"][0]["session_ids"] == [str(sessions[4].id)]
    assert result["comparisons"]["agents"][0]["label"] == "Support"
    assert result["comparisons"]["agents"][0]["known_outcomes"] == 6
    assert result["comparisons"]["agents"][0]["session_ids"]
    assert result["comparisons"]["versions"][0]["label"] == "3"
    assert {item["label"] for item in result["comparisons"]["platforms"]} == {
        "sdk",
        "vapi",
    }
    assert result["comparisons"]["providers"][0]["label"] == "openai"
    assert result["comparisons"]["models"][0]["label"] == "gpt-4o-mini"
    assert result["comparisons"]["models"][0]["session_ids"]
    assert result["outcome_sources"] == {"explicit": 3, "inferred": 3, "unknown": 0}
