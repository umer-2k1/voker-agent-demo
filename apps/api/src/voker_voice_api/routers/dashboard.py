import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.orm import Session

from voker_voice_api.analytics import latency_distribution
from voker_voice_api.bootstrap import create_ingest_key
from voker_voice_api.config import REPOSITORY_ROOT, get_settings
from voker_voice_api.connectors import (
    ConnectorError,
    configure_provider_resources,
    list_provider_resources,
)
from voker_voice_api.database import get_db
from voker_voice_api.models import (
    Agent,
    AgentRun,
    AgentVersion,
    AnalysisRun,
    APIKey,
    CostRecord,
    Environment,
    Error,
    Event,
    Finding,
    FindingEvidence,
    Integration,
    Job,
    Project,
    Recording,
    Span,
    Turn,
    UsageRecord,
    WebhookDelivery,
    WebhookReceipt,
)
from voker_voice_api.models import (
    Session as VoiceSession,
)
from voker_voice_api.recordings import (
    cloudinary_playback_url,
    external_playback_url,
    recording_expiry,
    validate_recording_metadata,
)
from voker_voice_api.routers.account import require_dashboard_user
from voker_voice_api.security import (
    decrypt_connector_secrets,
    encrypt_connector_secrets,
    generate_webhook_token,
)

router = APIRouter(
    prefix="/api", tags=["dashboard"], dependencies=[Depends(require_dashboard_user)]
)


def timestamp(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


def json_number(value: int | float | Decimal | None) -> float | int | None:
    return float(value) if isinstance(value, Decimal) else value


def project_for_slug(db: Session, project_slug: str) -> Project:
    project = db.scalar(select(Project).where(Project.slug == project_slug))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/projects/{project_slug}/api-keys")
def list_api_keys(project_slug: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    project = project_for_slug(db, project_slug)
    keys = db.scalars(
        select(APIKey, Environment)
        .join(Environment, APIKey.environment_id == Environment.id)
        .where(APIKey.project_id == project.id)
        .order_by(APIKey.created_at.desc())
    ).all()
    return {
        "items": [
            {
                "id": str(key.id),
                "label": key.label,
                "prefix": key.prefix,
                "environment": environment.slug,
                "created_at": timestamp(key.created_at),
                "last_used_at": timestamp(key.last_used_at),
                "revoked_at": timestamp(key.revoked_at),
            }
            for key, environment in keys
        ]
    }


@router.post("/projects/{project_slug}/api-keys", status_code=201)
def create_api_key(
    project_slug: str, payload: dict[str, str] = Body(...), db: Session = Depends(get_db)
) -> dict[str, str]:
    project = project_for_slug(db, project_slug)
    environment = db.scalar(
        select(Environment).where(
            Environment.project_id == project.id,
            Environment.slug == payload.get("environment", "development"),
        )
    )
    label = payload.get("label", "")
    if environment is None or not label:
        raise HTTPException(
            status_code=422, detail="A valid environment and key label are required"
        )
    generated = create_ingest_key(db, project=project, environment=environment, label=label)
    db.commit()
    return {"prefix": generated.prefix, "api_key": generated.raw}


@router.post("/projects/{project_slug}/api-keys/{key_id}/revoke")
def revoke_api_key(
    project_slug: str, key_id: UUID, db: Session = Depends(get_db)
) -> dict[str, str]:
    project = project_for_slug(db, project_slug)
    key = db.scalar(select(APIKey).where(APIKey.id == key_id, APIKey.project_id == project.id))
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found")
    key.revoked_at = datetime.now(UTC)
    db.commit()
    return {"id": str(key.id), "status": "revoked"}


@router.get("/projects/{project_slug}/integrations")
def list_integrations(project_slug: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    project = project_for_slug(db, project_slug)
    integrations = db.scalars(
        select(Integration)
        .where(Integration.project_id == project.id)
        .order_by(Integration.created_at.desc(), Integration.id.desc())
    ).all()
    return {"items": [integration_summary(db, item) for item in integrations]}


def integration_summary(db: Session, item: Integration) -> dict[str, Any]:
    latest_receipt = db.scalar(
        select(WebhookReceipt)
        .where(WebhookReceipt.integration_id == item.id)
        .order_by(WebhookReceipt.received_at.desc())
        .limit(1)
    )
    delivery_failures = (
        db.scalar(
            select(func.count())
            .select_from(WebhookDelivery)
            .where(
                WebhookDelivery.integration_id == item.id,
                WebhookDelivery.status.in_(("pending", "retry", "failed")),
            )
        )
        or 0
    )
    return {
        "id": str(item.id),
        "provider": item.provider,
        "external_id": item.external_id,
        "name": item.name,
        "status": item.status,
        "selected_resources": item.config.get("selected_resources", []),
        "webhook_url": item.config.get("webhook_url"),
        "forwarding_enabled": bool(item.config.get("forwarding_enabled", True)),
        "forwarding_destinations": item.config.get("forwarding_destinations", []),
        "forwarding_failures": delivery_failures,
        "last_delivery_at": timestamp(latest_receipt.received_at) if latest_receipt else None,
        "normalization_state": (
            "processed"
            if latest_receipt and latest_receipt.processed_at
            else "pending"
            if latest_receipt
            else "not_yet_observed"
        ),
    }


@router.post("/projects/{project_slug}/integrations", status_code=201)
def create_integration(
    project_slug: str,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Validate and store a managed provider credential."""

    project = project_for_slug(db, project_slug)
    provider = payload.get("provider", "")
    name = payload.get("name", "")
    external_id = payload.get("external_id")
    if provider not in {"vapi", "retell"} or not name:
        raise HTTPException(status_code=422, detail="provider (vapi/retell) and name are required")
    token = generate_webhook_token()
    api_key = payload.get("api_key")
    resources: list[dict[str, Any]] = []
    encrypted_credentials = None
    integration_status = "pending"
    if isinstance(api_key, str) and api_key:
        try:
            resources = list_provider_resources(provider, api_key)
        except ConnectorError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        encrypted_credentials = encrypt_connector_secrets(
            {"api_key": api_key, "webhook_token": token.raw}
        )
        integration_status = "pending_configuration"
    integration = Integration(
        project_id=project.id,
        provider=provider,
        external_id=external_id or None,
        name=name,
        status=integration_status,
        encrypted_credentials=encrypted_credentials,
        config={
            "webhook_token_hash": token.secret_hash,
            "available_resources": resources,
            "selected_resources": [],
            "agent_mappings": {},
            "forwarding_enabled": True,
        },
    )
    db.add(integration)
    db.commit()
    return {
        "id": str(integration.id),
        "provider": provider,
        "status": integration.status,
        "resources": resources,
        "webhook_token": token.raw if encrypted_credentials is None else None,
    }


def managed_integration(db: Session, project_id: UUID, integration_id: UUID) -> Integration:
    integration = db.scalar(
        select(Integration).where(
            Integration.id == integration_id, Integration.project_id == project_id
        )
    )
    if integration is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    return integration


@router.get("/projects/{project_slug}/integrations/{integration_id}/resources")
def integration_resources(
    project_slug: str, integration_id: UUID, db: Session = Depends(get_db)
) -> dict[str, Any]:
    project = project_for_slug(db, project_slug)
    integration = managed_integration(db, project.id, integration_id)
    try:
        api_key = decrypt_connector_secrets(integration.encrypted_credentials)["api_key"]
        resources = list_provider_resources(integration.provider, api_key)
    except (ConnectorError, KeyError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    integration.config = {**integration.config, "available_resources": resources}
    db.commit()
    return {"items": resources}


@router.post("/projects/{project_slug}/integrations/{integration_id}/configure")
def configure_integration(
    project_slug: str,
    integration_id: UUID,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = project_for_slug(db, project_slug)
    integration = managed_integration(db, project.id, integration_id)
    selected_ids = payload.get("selected_ids")
    public_base_url = payload.get("public_base_url")
    environment_slug = payload.get("environment", "development")
    if (
        not isinstance(selected_ids, list)
        or not selected_ids
        or not all(isinstance(item, str) for item in selected_ids)
    ):
        raise HTTPException(status_code=422, detail="Select at least one assistant or agent")
    if not isinstance(public_base_url, str):
        raise HTTPException(status_code=422, detail="A public API base URL is required")
    parsed = urlparse(public_base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="Public API base URL must be http(s)")
    environment = db.scalar(
        select(Environment).where(
            Environment.project_id == project.id,
            Environment.slug == environment_slug,
        )
    )
    if environment is None:
        raise HTTPException(status_code=422, detail="Unknown environment")
    try:
        secrets = decrypt_connector_secrets(integration.encrypted_credentials)
        resources = list_provider_resources(integration.provider, secrets["api_key"])
        webhook_url = (
            f"{public_base_url.rstrip('/')}/v1/webhooks/{integration.provider}/{integration.id}"
        )
        forwarding_urls = configure_provider_resources(
            integration.provider,
            secrets["api_key"],
            resources,
            selected_ids,
            webhook_url=webhook_url,
            webhook_token=secrets["webhook_token"],
        )
    except (ConnectorError, KeyError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    by_id = {str(item["id"]): item for item in resources}
    mappings: dict[str, dict[str, str | None]] = {}
    selected_resources: list[dict[str, Any]] = []
    for external_id in selected_ids:
        resource = by_id[external_id]
        selected_resources.append(resource)
        slug = re.sub(r"[^a-z0-9]+", "-", str(resource["name"]).lower()).strip("-")[:100]
        agent = db.scalar(select(Agent).where(Agent.project_id == project.id, Agent.slug == slug))
        if agent is None:
            agent = Agent(
                project_id=project.id,
                name=str(resource["name"]),
                slug=slug or f"{integration.provider}-agent",
                source=integration.provider,
                external_id=external_id,
            )
            db.add(agent)
        mappings[external_id] = {
            "name": str(resource["name"]),
            "version": resource.get("version"),
        }
    integration.status = "active"
    integration.config = {
        **integration.config,
        "environment_id": str(environment.id),
        "environment": environment.slug,
        "available_resources": resources,
        "selected_resources": selected_resources,
        "agent_mappings": mappings,
        "webhook_url": webhook_url,
        "forwarding_destinations": forwarding_urls,
        "forwarding_enabled": bool(payload.get("forwarding_enabled", True)),
    }
    db.commit()
    return integration_summary(db, integration)


@router.patch("/projects/{project_slug}/integrations/{integration_id}")
def update_integration(
    project_slug: str,
    integration_id: UUID,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = project_for_slug(db, project_slug)
    integration = managed_integration(db, project.id, integration_id)
    if "enabled" in payload:
        integration.status = "active" if bool(payload["enabled"]) else "disabled"
    if "forwarding_enabled" in payload:
        integration.config = {
            **integration.config,
            "forwarding_enabled": bool(payload["forwarding_enabled"]),
        }
    db.commit()
    return integration_summary(db, integration)


def session_summary(session: VoiceSession, error_count: int, event_count: int) -> dict[str, Any]:
    return {
        "id": str(session.id),
        "external_session_id": session.external_session_id,
        "trace_id": session.trace_id,
        "source": session.source,
        "status": session.status,
        "outcome": session.outcome,
        "outcome_source": session.outcome_source,
        "started_at": timestamp(session.started_at),
        "ended_at": timestamp(session.ended_at),
        "error_count": error_count,
        "event_count": event_count,
        "duration_ms": (
            max(0, round((session.ended_at - session.started_at).total_seconds() * 1000))
            if session.ended_at
            else None
        ),
    }


@router.get("/projects")
def list_projects(db: Session = Depends(get_db)) -> dict[str, Any]:
    projects = db.scalars(select(Project).order_by(Project.name, Project.id)).all()
    return {
        "items": [
            {"id": str(project.id), "name": project.name, "slug": project.slug}
            for project in projects
        ]
    }


@router.get("/projects/{project_slug}/setup")
def project_setup(project_slug: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return observed integration state separately from setup instructions."""

    project = project_for_slug(db, project_slug)
    environments = db.scalars(
        select(Environment)
        .where(Environment.project_id == project.id)
        .order_by(Environment.name, Environment.id)
    ).all()
    integrations = db.scalars(
        select(Integration)
        .where(Integration.project_id == project.id)
        .order_by(Integration.provider, Integration.name)
    ).all()
    latest_event = db.scalar(
        select(Event)
        .where(Event.project_id == project.id)
        .order_by(Event.received_at.desc(), Event.id.desc())
        .limit(1)
    )
    observed_types = set(
        db.scalars(
            select(Event.event_type).where(Event.project_id == project.id).distinct().limit(500)
        )
    )
    stage_prefixes = ("stt", "llm", "tool", "mcp", "graph", "agent", "tts", "playback")
    observed_stages = [
        stage
        for stage in stage_prefixes
        if any(
            event_type == stage or event_type.startswith(f"{stage}.")
            for event_type in observed_types
        )
    ]
    return {
        "project": {"id": str(project.id), "name": project.name, "slug": project.slug},
        "environments": [
            {"id": str(environment.id), "name": environment.name, "slug": environment.slug}
            for environment in environments
        ],
        "integrations": [integration_summary(db, integration) for integration in integrations],
        "last_received_event_at": timestamp(latest_event.received_at) if latest_event else None,
        "observed_stages": observed_stages,
    }


@router.get("/projects/{project_slug}/overview")
def project_overview(project_slug: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    project = project_for_slug(db, project_slug)
    total_sessions = (
        db.scalar(
            select(func.count())
            .select_from(VoiceSession)
            .where(VoiceSession.project_id == project.id)
        )
        or 0
    )
    active_sessions = (
        db.scalar(
            select(func.count())
            .select_from(VoiceSession)
            .where(VoiceSession.project_id == project.id, VoiceSession.status == "in_progress")
        )
        or 0
    )
    errors = (
        db.scalar(
            select(func.count())
            .select_from(Error)
            .join(VoiceSession, Error.session_id == VoiceSession.id)
            .where(VoiceSession.project_id == project.id)
        )
        or 0
    )
    durations = db.scalars(
        select(Span.duration_ms)
        .join(VoiceSession, Span.session_id == VoiceSession.id)
        .where(VoiceSession.project_id == project.id, Span.duration_ms.is_not(None))
    ).all()
    duration_values = [float(item) for item in durations if item is not None]
    avg_duration = sum(duration_values) / len(duration_values) if duration_values else None
    return {
        "project": {"id": str(project.id), "name": project.name, "slug": project.slug},
        "metrics": {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "error_count": errors,
            "average_span_duration_ms": avg_duration,
        },
    }


@router.get("/projects/{project_slug}/settings")
def project_settings(project_slug: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    project = project_for_slug(db, project_slug)
    return {
        "semantic_analysis_enabled": project.semantic_analysis_enabled,
        "semantic_content_exclusions": project.semantic_content_exclusions,
    }


@router.patch("/projects/{project_slug}/settings")
def update_project_settings(
    project_slug: str,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = project_for_slug(db, project_slug)
    if "semantic_analysis_enabled" in payload:
        enabled = payload["semantic_analysis_enabled"]
        if not isinstance(enabled, bool):
            raise HTTPException(status_code=422, detail="semantic_analysis_enabled must be boolean")
        project.semantic_analysis_enabled = enabled
    if "semantic_content_exclusions" in payload:
        exclusions = payload["semantic_content_exclusions"]
        if (
            not isinstance(exclusions, list)
            or len(exclusions) > 25
            or any(not isinstance(item, str) or not item.strip() for item in exclusions)
        ):
            raise HTTPException(
                status_code=422,
                detail="semantic_content_exclusions must contain up to 25 non-empty field names",
            )
        project.semantic_content_exclusions = list(
            dict.fromkeys(item.strip() for item in exclusions)
        )
    db.commit()
    return {
        "semantic_analysis_enabled": project.semantic_analysis_enabled,
        "semantic_content_exclusions": project.semantic_content_exclusions,
    }


@router.get("/projects/{project_slug}/analytics/overview")
def analytics_overview(
    project_slug: str,
    environment: str | None = None,
    started_after: datetime | None = None,
    started_before: datetime | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Database-bounded aggregates that retain unobserved values as unknown."""

    project = project_for_slug(db, project_slug)
    conditions = [VoiceSession.project_id == project.id]
    if environment:
        conditions.append(
            VoiceSession.environment_id.in_(
                select(Environment.id).where(
                    Environment.project_id == project.id,
                    Environment.slug == environment,
                )
            )
        )
    if started_after:
        conditions.append(VoiceSession.started_at >= started_after)
    if started_before:
        conditions.append(VoiceSession.started_at <= started_before)

    filtered = (
        select(
            VoiceSession.id.label("id"),
            VoiceSession.status.label("status"),
            VoiceSession.outcome.label("outcome"),
            VoiceSession.outcome_source.label("outcome_source"),
            VoiceSession.source.label("source"),
            VoiceSession.agent_id.label("agent_id"),
            VoiceSession.agent_version_id.label("agent_version_id"),
        )
        .where(*conditions)
        .subquery("filtered_sessions")
    )
    resolved_values = ("success", "resolved")
    terminal = db.execute(
        select(
            func.count().label("sessions"),
            func.sum(case((filtered.c.status == "completed", 1), else_=0)).label("completed"),
            func.sum(case((filtered.c.outcome.is_not(None), 1), else_=0)).label("known_outcomes"),
            func.sum(case((filtered.c.outcome.in_(resolved_values), 1), else_=0)).label("resolved"),
            func.sum(case((filtered.c.outcome == "escalated", 1), else_=0)).label("escalated"),
            func.sum(case((filtered.c.outcome == "abandoned", 1), else_=0)).label("abandoned"),
        ).select_from(filtered)
    ).one()
    session_count = int(terminal.sessions or 0)
    completed_count = int(terminal.completed or 0)
    known_outcome_count = int(terminal.known_outcomes or 0)

    outcome_counts = {
        str(label): int(count)
        for label, count in db.execute(
            select(filtered.c.outcome, func.count())
            .where(filtered.c.outcome.is_not(None))
            .group_by(filtered.c.outcome)
        )
    }
    source_counts = {
        str(label): int(count)
        for label, count in db.execute(
            select(filtered.c.source, func.count()).group_by(filtered.c.source)
        )
    }

    cost_row = db.execute(
        select(
            func.count(CostRecord.id).label("records"),
            func.sum(CostRecord.amount_micros).label("amount"),
            func.sum(
                case((CostRecord.is_estimate.is_(True), CostRecord.amount_micros), else_=0)
            ).label("estimated_amount"),
            func.sum(
                case((CostRecord.is_estimate.is_(False), CostRecord.amount_micros), else_=0)
            ).label("exact_amount"),
            func.sum(case((CostRecord.is_estimate.is_(True), 1), else_=0)).label(
                "estimated_records"
            ),
            func.sum(case((CostRecord.is_estimate.is_(False), 1), else_=0)).label("exact_records"),
        )
        .select_from(CostRecord)
        .join(filtered, CostRecord.session_id == filtered.c.id)
    ).one()
    usage_row = db.execute(
        select(
            func.sum(UsageRecord.input_tokens).label("input_tokens"),
            func.sum(UsageRecord.output_tokens).label("output_tokens"),
            func.sum(UsageRecord.total_tokens).label("total_tokens"),
            func.sum(UsageRecord.audio_seconds).label("audio_seconds"),
            func.sum(UsageRecord.tts_characters).label("tts_characters"),
        )
        .select_from(UsageRecord)
        .join(filtered, UsageRecord.session_id == filtered.c.id)
    ).one()

    def distinct_count_and_links(
        entity: type[Event] | type[Span] | type[Error], predicate: Any
    ) -> tuple[int, list[str]]:
        query = (
            select(entity.session_id)
            .join(filtered, entity.session_id == filtered.c.id)
            .where(predicate)
            .distinct()
        )
        count = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        links = [str(item) for item in db.scalars(query.limit(10))]
        return int(count), links

    correction_count, correction_links = distinct_count_and_links(
        Event, Event.event_type.startswith("correction.")
    )
    interruption_count, interruption_links = distinct_count_and_links(
        Event, Event.event_type == "voice.interruption"
    )
    dead_air_count, dead_air_links = distinct_count_and_links(
        Event, Event.event_type.in_(("voice.dead_air", "voice.dead-air"))
    )
    talk_over_count, talk_over_links = distinct_count_and_links(
        Event, Event.event_type.in_(("voice.talk_over", "voice.talk-over"))
    )
    error_count, error_links = distinct_count_and_links(Error, Error.id.is_not(None))
    tool_failure_count, tool_failure_links = distinct_count_and_links(
        Span,
        Span.kind.in_(("tool", "mcp"))
        & Span.status.in_(("error", "failed", "timeout", "cancelled")),
    )
    abandoned_query = (
        select(filtered.c.id)
        .select_from(filtered)
        .outerjoin(Event, Event.session_id == filtered.c.id)
        .where(
            or_(
                filtered.c.outcome == "abandoned",
                Event.event_type.startswith("abandonment."),
            )
        )
        .distinct()
    )
    abandoned_total = int(
        db.scalar(select(func.count()).select_from(abandoned_query.subquery())) or 0
    )
    abandonment_links = [str(item) for item in db.scalars(abandoned_query.limit(10))]

    event_metrics = (
        select(
            Event.session_id.label("session_id"),
            func.sum(case((Event.event_type == "voice.interruption", 1), else_=0)).label(
                "interruptions"
            ),
            func.sum(
                case(
                    (Event.event_type.in_(("voice.dead_air", "voice.dead-air")), 1),
                    else_=0,
                )
            ).label("dead_air"),
            func.max(
                case((Event.event_type == "stt.completed", Event.duration_ms), else_=None)
            ).label("stt_duration_ms"),
        )
        .join(filtered, Event.session_id == filtered.c.id)
        .group_by(Event.session_id)
        .subquery("event_metrics")
    )
    cohort_rows = (
        select(
            filtered.c.id.label("id"),
            filtered.c.outcome.label("outcome"),
            func.coalesce(event_metrics.c.interruptions, 0).label("interruptions"),
            func.coalesce(event_metrics.c.dead_air, 0).label("dead_air"),
            event_metrics.c.stt_duration_ms.label("stt_duration_ms"),
        )
        .outerjoin(event_metrics, event_metrics.c.session_id == filtered.c.id)
        .subquery("cohort_rows")
    )

    def cohort(predicate: Any) -> dict[str, Any] | None:
        observed = cohort_rows.c.outcome.is_not(None) & predicate
        row = db.execute(
            select(
                func.count().label("sample_size"),
                func.sum(case((cohort_rows.c.outcome.in_(resolved_values), 1), else_=0)).label(
                    "resolved"
                ),
            )
            .select_from(cohort_rows)
            .where(observed)
        ).one()
        sample_size = int(row.sample_size or 0)
        if sample_size < 5:
            return None
        resolved = int(row.resolved or 0)
        links = [
            str(item)
            for item in db.scalars(
                select(cohort_rows.c.id).where(observed).order_by(cohort_rows.c.id).limit(10)
            )
        ]
        return {
            "sample_size": sample_size,
            "resolved": resolved,
            "resolution_rate": resolved / sample_size,
            "session_ids": links,
        }

    voice_cohorts = {
        "high_interruption": cohort(cohort_rows.c.interruptions >= 3),
        "normal_interruption": cohort(cohort_rows.c.interruptions <= 1),
        "slow_stt": cohort(cohort_rows.c.stt_duration_ms > 1200),
        "fast_stt": cohort(cohort_rows.c.stt_duration_ms <= 500),
        "dead_air": cohort(cohort_rows.c.dead_air >= 1),
        "no_dead_air": cohort(cohort_rows.c.dead_air == 0),
    }

    latency: dict[str, Any] = {}
    for kind in ("stt", "llm", "tool", "tts", "voice"):
        values = [
            float(value)
            for value in db.scalars(
                select(Span.duration_ms)
                .join(filtered, Span.session_id == filtered.c.id)
                .where(Span.kind == kind, Span.duration_ms.is_not(None))
                .order_by(Span.duration_ms)
                .limit(10_000)
            )
            if value is not None
        ]
        latency[kind] = latency_distribution(values)

    failure_rows = db.execute(
        select(Finding.type, func.count(Finding.id))
        .join(filtered, Finding.session_id == filtered.c.id)
        .group_by(Finding.type)
        .order_by(func.count(Finding.id).desc())
        .limit(8)
    ).all()
    failure_categories = {str(category): int(count) for category, count in failure_rows}
    failure_category_insights = []
    for category, count in failure_rows:
        links = [
            str(item)
            for item in db.scalars(
                select(Finding.session_id)
                .join(filtered, Finding.session_id == filtered.c.id)
                .where(Finding.type == category)
                .distinct()
                .limit(10)
            )
        ]
        failure_category_insights.append(
            {"category": category, "count": int(count), "session_ids": links}
        )

    def comparison_rows(statement: Any) -> list[dict[str, Any]]:
        rows = db.execute(statement).all()
        return [
            {
                "label": str(label),
                "sessions": int(sessions),
                "resolved": int(resolved or 0),
                "resolution_rate": int(resolved or 0) / int(sessions),
            }
            for label, sessions, resolved in rows
            if sessions
        ]

    resolved_case = case((filtered.c.outcome.in_(resolved_values), 1), else_=0)
    agents = comparison_rows(
        select(
            func.coalesce(Agent.name, "Unknown agent"),
            func.count(filtered.c.id),
            func.sum(resolved_case),
        )
        .select_from(filtered)
        .outerjoin(Agent, Agent.id == filtered.c.agent_id)
        .group_by(Agent.name)
        .order_by(func.count(filtered.c.id).desc())
        .limit(20)
    )
    versions = comparison_rows(
        select(
            func.coalesce(AgentVersion.version, "Unknown version"),
            func.count(filtered.c.id),
            func.sum(resolved_case),
        )
        .select_from(filtered)
        .outerjoin(AgentVersion, AgentVersion.id == filtered.c.agent_version_id)
        .group_by(AgentVersion.version)
        .order_by(func.count(filtered.c.id).desc())
        .limit(20)
    )
    platforms = comparison_rows(
        select(filtered.c.source, func.count(filtered.c.id), func.sum(resolved_case))
        .select_from(filtered)
        .group_by(filtered.c.source)
        .order_by(func.count(filtered.c.id).desc())
        .limit(20)
    )
    usage_sessions = (
        select(
            UsageRecord.session_id.label("session_id"),
            func.coalesce(UsageRecord.provider, "Unknown provider").label("provider"),
            func.coalesce(UsageRecord.model, "Unknown model").label("model"),
            filtered.c.outcome.label("outcome"),
        )
        .join(filtered, UsageRecord.session_id == filtered.c.id)
        .distinct()
        .subquery("usage_sessions")
    )
    usage_resolved = case((usage_sessions.c.outcome.in_(resolved_values), 1), else_=0)
    providers = comparison_rows(
        select(
            usage_sessions.c.provider,
            func.count(),
            func.sum(usage_resolved),
        )
        .select_from(usage_sessions)
        .group_by(usage_sessions.c.provider)
        .order_by(func.count().desc())
        .limit(20)
    )
    models = comparison_rows(
        select(usage_sessions.c.model, func.count(), func.sum(usage_resolved))
        .select_from(usage_sessions)
        .group_by(usage_sessions.c.model)
        .order_by(func.count().desc())
        .limit(20)
    )

    outcome_source_rows = {
        label: int(count)
        for label, count in db.execute(
            select(filtered.c.outcome_source, func.count()).group_by(filtered.c.outcome_source)
        )
    }
    explicit_outcomes = sum(outcome_source_rows.get(value, 0) for value in ("explicit", "provider"))
    inferred_outcomes = sum(
        outcome_source_rows.get(value, 0) for value in ("semantic", "rule", "inferred")
    )
    unknown_outcomes = session_count - explicit_outcomes - inferred_outcomes

    def ratio(numerator: int, denominator: int) -> float | None:
        return numerator / denominator if denominator else None

    return {
        "filters": {
            "environment": environment,
            "started_after": timestamp(started_after),
            "started_before": timestamp(started_before),
        },
        "session_count": session_count,
        "completed_session_count": completed_count,
        "outcomes": outcome_counts,
        "sources": source_counts,
        "cost": {
            "amount_micros": int(cost_row.amount) if cost_row.amount is not None else None,
            "exact_amount_micros": int(cost_row.exact_amount or 0),
            "estimated_amount_micros": int(cost_row.estimated_amount or 0),
            "currency": "USD" if cost_row.records else None,
            "record_count": int(cost_row.records or 0),
            "estimated_record_count": int(cost_row.estimated_records or 0),
            "exact_record_count": int(cost_row.exact_records or 0),
        },
        "usage": {
            "input_tokens": usage_row.input_tokens,
            "output_tokens": usage_row.output_tokens,
            "total_tokens": usage_row.total_tokens,
            "audio_seconds": json_number(usage_row.audio_seconds),
            "tts_characters": usage_row.tts_characters,
        },
        "voice_impact_cohorts": voice_cohorts,
        "latency": latency,
        "latency_sample_limit_per_stage": 10_000,
        "rates": {
            "resolution": ratio(int(terminal.resolved or 0), known_outcome_count),
            "correction": ratio(correction_count, session_count),
            "escalation": ratio(int(terminal.escalated or 0), session_count),
            "abandonment": ratio(abandoned_total, session_count),
            "error": ratio(error_count, session_count),
        },
        "failure_categories": failure_categories,
        "failure_category_insights": failure_category_insights,
        "tool_failure_count": tool_failure_count,
        "voice_behavior": {
            "interruption_sessions": interruption_count,
            "talk_over_sessions": talk_over_count,
            "dead_air_sessions": dead_air_count,
            "correction_sessions": correction_count,
        },
        "insights": [
            {
                "key": "errors",
                "label": "Sessions with recorded errors",
                "count": error_count,
                "session_ids": error_links,
            },
            {
                "key": "tool_failures",
                "label": "Sessions with failed tools",
                "count": tool_failure_count,
                "session_ids": tool_failure_links,
            },
            {
                "key": "corrections",
                "label": "Sessions with observed corrections",
                "count": correction_count,
                "session_ids": correction_links,
            },
            {
                "key": "abandonment",
                "label": "Sessions with observed abandonment",
                "count": abandoned_total,
                "session_ids": abandonment_links,
            },
            {
                "key": "interruptions",
                "label": "Sessions with observed interruptions",
                "count": interruption_count,
                "session_ids": interruption_links,
            },
            {
                "key": "dead_air",
                "label": "Sessions with observed dead air",
                "count": dead_air_count,
                "session_ids": dead_air_links,
            },
            {
                "key": "talk_over",
                "label": "Sessions with observed talk-over",
                "count": talk_over_count,
                "session_ids": talk_over_links,
            },
        ],
        "comparisons": {
            "agents": agents,
            "versions": versions,
            "platforms": platforms,
            "providers": providers,
            "models": models,
        },
        "outcome_sources": {
            "explicit": explicit_outcomes,
            "inferred": inferred_outcomes,
            "unknown": unknown_outcomes,
        },
    }


@router.get("/projects/{project_slug}/sessions")
def list_sessions(
    project_slug: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: str | None = None,
    source: str | None = None,
    environment: str | None = None,
    agent: str | None = None,
    version: str | None = None,
    outcome: str | None = None,
    has_error: bool | None = None,
    started_after: datetime | None = None,
    started_before: datetime | None = None,
    min_latency_ms: Annotated[float | None, Query(ge=0)] = None,
    max_latency_ms: Annotated[float | None, Query(ge=0)] = None,
    search: Annotated[str | None, Query(max_length=255)] = None,
    sort: Annotated[
        str,
        Query(pattern="^(started_at_desc|started_at_asc|errors_desc|events_desc)$"),
    ] = "started_at_desc",
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = project_for_slug(db, project_slug)
    conditions = [VoiceSession.project_id == project.id]
    if status:
        conditions.append(VoiceSession.status == status)
    if source:
        conditions.append(VoiceSession.source == source)
    if environment:
        conditions.append(
            VoiceSession.environment_id.in_(
                select(Environment.id).where(
                    Environment.project_id == project.id,
                    Environment.slug == environment,
                )
            )
        )
    if agent:
        conditions.append(
            VoiceSession.agent_id.in_(
                select(Agent.id).where(
                    Agent.project_id == project.id,
                    (Agent.slug == agent) | (Agent.name == agent),
                )
            )
        )
    if version:
        conditions.append(
            VoiceSession.agent_version_id.in_(
                select(AgentVersion.id).where(AgentVersion.version == version)
            )
        )
    if outcome:
        conditions.append(VoiceSession.outcome == outcome)
    if has_error is not None:
        error_exists = exists(select(Error.id).where(Error.session_id == VoiceSession.id))
        conditions.append(error_exists if has_error else ~error_exists)
    if started_after:
        conditions.append(VoiceSession.started_at >= started_after)
    if started_before:
        conditions.append(VoiceSession.started_at <= started_before)
    if min_latency_ms is not None:
        conditions.append(
            exists(
                select(Span.id).where(
                    Span.session_id == VoiceSession.id,
                    Span.duration_ms >= min_latency_ms,
                )
            )
        )
    if max_latency_ms is not None:
        conditions.append(
            ~exists(
                select(Span.id).where(
                    Span.session_id == VoiceSession.id,
                    Span.duration_ms > max_latency_ms,
                )
            )
        )
    if search:
        conditions.append(VoiceSession.external_session_id.ilike(f"%{search}%"))
    total = db.scalar(select(func.count()).select_from(VoiceSession).where(*conditions)) or 0
    ordering = {
        "started_at_desc": (VoiceSession.started_at.desc(), VoiceSession.id.desc()),
        "started_at_asc": (VoiceSession.started_at.asc(), VoiceSession.id.asc()),
    }
    # Error/event ordering uses correlated counts so sorting remains server-side
    # and therefore stable across pagination.
    order_by: tuple[Any, ...]
    if sort == "errors_desc":
        error_total = (
            select(func.count())
            .select_from(Error)
            .where(Error.session_id == VoiceSession.id)
            .correlate(VoiceSession)
            .scalar_subquery()
        )
        order_by = (error_total.desc(), VoiceSession.started_at.desc(), VoiceSession.id.desc())
    elif sort == "events_desc":
        event_total = (
            select(func.count())
            .select_from(Event)
            .where(Event.session_id == VoiceSession.id)
            .correlate(VoiceSession)
            .scalar_subquery()
        )
        order_by = (event_total.desc(), VoiceSession.started_at.desc(), VoiceSession.id.desc())
    else:
        order_by = ordering[sort]
    sessions = db.scalars(
        select(VoiceSession).where(*conditions).order_by(*order_by).offset(offset).limit(limit)
    ).all()
    items = []
    for session in sessions:
        error_count = (
            db.scalar(select(func.count()).select_from(Error).where(Error.session_id == session.id))
            or 0
        )
        event_count = (
            db.scalar(select(func.count()).select_from(Event).where(Event.session_id == session.id))
            or 0
        )
        summary = session_summary(session, error_count, event_count)
        environment_row = db.get(Environment, session.environment_id)
        agent_row = db.get(Agent, session.agent_id) if session.agent_id else None
        version_row = (
            db.get(AgentVersion, session.agent_version_id) if session.agent_version_id else None
        )
        summary.update(
            {
                "environment": environment_row.slug if environment_row else None,
                "agent": agent_row.slug if agent_row else None,
                "agent_version": version_row.version if version_row else None,
            }
        )
        items.append(summary)
    return {"items": items, "page": {"offset": offset, "limit": limit, "total": total}}


@router.get("/projects/{project_slug}/sessions/{session_id}")
def get_session_trace(
    project_slug: str,
    session_id: UUID,
    db: Session = Depends(get_db),
    event_limit: Annotated[int, Query(ge=1, le=500)] = 250,
    event_offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    project = project_for_slug(db, project_slug)
    session = db.scalar(
        select(VoiceSession).where(
            VoiceSession.project_id == project.id, VoiceSession.id == session_id
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    event_total = (
        db.scalar(select(func.count()).select_from(Event).where(Event.session_id == session.id))
        or 0
    )
    behavior_types = {
        "interruptions": ("voice.interruption",),
        "talk_over": ("voice.talk_over",),
        "dead_air": ("voice.dead_air",),
        "corrections": ("correction.started", "correction.completed"),
        "abandonment": ("abandonment.detected", "turn.abandoned"),
    }
    voice_behavior = {
        label: (
            db.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.session_id == session.id, Event.event_type.in_(event_types))
            )
            or 0
        )
        for label, event_types in behavior_types.items()
    }
    events = db.scalars(
        select(Event)
        .where(Event.session_id == session.id)
        .order_by(Event.occurred_at, Event.sequence, Event.id)
        .offset(event_offset)
        .limit(event_limit)
    ).all()
    spans = db.scalars(
        select(Span)
        .where(Span.session_id == session.id)
        .order_by(Span.started_at, Span.id)
        .limit(500)
    ).all()
    errors = db.scalars(
        select(Error)
        .where(Error.session_id == session.id)
        .order_by(Error.created_at, Error.id)
        .limit(250)
    ).all()
    usage = db.scalars(
        select(UsageRecord).where(UsageRecord.session_id == session.id).limit(250)
    ).all()
    costs = db.scalars(
        select(CostRecord).where(CostRecord.session_id == session.id).limit(250)
    ).all()
    findings = db.scalars(
        select(Finding)
        .where(Finding.session_id == session.id)
        .order_by(Finding.created_at.desc())
        .limit(250)
    ).all()
    analysis_runs = db.scalars(
        select(AnalysisRun)
        .where(AnalysisRun.session_id == session.id)
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        .limit(100)
    ).all()
    recordings = db.scalars(
        select(Recording)
        .where(Recording.session_id == session.id)
        .order_by(Recording.created_at)
        .limit(100)
    ).all()
    turns = db.scalars(
        select(Turn)
        .where(Turn.session_id == session.id)
        .order_by(Turn.sequence, Turn.id)
        .limit(500)
    ).all()
    agent_runs = db.scalars(
        select(AgentRun)
        .where(AgentRun.session_id == session.id)
        .order_by(AgentRun.started_at, AgentRun.id)
        .limit(500)
    ).all()
    agents_by_id = {
        agent_id: agent
        for agent_id in {run.agent_id for run in agent_runs if run.agent_id}
        if (agent := db.get(Agent, agent_id)) is not None
    }
    versions_by_id = {
        version_id: version
        for version_id in {run.agent_version_id for run in agent_runs if run.agent_version_id}
        if (version := db.get(AgentVersion, version_id)) is not None
    }
    event_by_id = {event.id: event for event in events}
    span_by_id = {span.id: span for span in spans}
    turn_ids = {turn.id for turn in turns}

    def evidence_target(evidence: FindingEvidence) -> dict[str, str | None]:
        """Resolve opaque evidence rows to directly addressable trace targets."""
        event_id = None
        span_id = None
        turn_id = None
        if evidence.entity_type == "event":
            event = event_by_id.get(evidence.entity_id)
            event_id = str(event.id) if event else None
            turn_id = str(event.turn_id) if event and event.turn_id else None
        elif evidence.entity_type == "span":
            span = span_by_id.get(evidence.entity_id)
            span_id = str(span.id) if span else None
            turn_id = str(span.turn_id) if span and span.turn_id else None
            related_event = next(
                (event for event in events if event.span_id == evidence.entity_id), None
            )
            event_id = str(related_event.id) if related_event else None
        elif evidence.entity_type == "turn" and evidence.entity_id in turn_ids:
            turn_id = str(evidence.entity_id)
        return {
            "entity_type": evidence.entity_type,
            "entity_id": str(evidence.entity_id),
            "event_id": event_id,
            "span_id": span_id,
            "turn_id": turn_id,
        }

    return {
        "session": session_summary(session, len(errors), event_total),
        "event_page": {"offset": event_offset, "limit": event_limit, "total": event_total},
        "voice_behavior": voice_behavior,
        "events": [
            {
                "id": str(event.id),
                "event_id": event.event_id,
                "event_type": event.event_type,
                "status": event.status,
                "occurred_at": timestamp(event.occurred_at),
                "duration_ms": json_number(event.duration_ms),
                "payload": event.payload,
            }
            for event in events
        ],
        "turns": [
            {
                "id": str(turn.id),
                "external_turn_id": turn.external_turn_id,
                "sequence": turn.sequence,
                "speaker": turn.speaker,
                "started_at": timestamp(turn.started_at),
                "ended_at": timestamp(turn.ended_at),
                "transcript": turn.transcript,
                "attributes": turn.attributes,
            }
            for turn in turns
        ],
        "spans": [
            {
                "id": str(span.id),
                "external_span_id": span.external_span_id,
                "parent_external_span_id": span.parent_external_span_id,
                "name": span.name,
                "kind": span.kind,
                "status": span.status,
                "source": span.source,
                "turn_id": str(span.turn_id) if span.turn_id else None,
                "agent_run_id": str(span.agent_run_id) if span.agent_run_id else None,
                "started_at": timestamp(span.started_at),
                "ended_at": timestamp(span.ended_at),
                "duration_ms": json_number(span.duration_ms),
                "attributes": span.attributes,
                "input": span.input_,
                "output": span.output,
            }
            for span in spans
        ],
        "agent_runs": [
            {
                "id": str(run.id),
                "external_run_id": run.external_run_id,
                "parent_run_id": str(run.parent_run_id) if run.parent_run_id else None,
                "turn_id": str(run.turn_id) if run.turn_id else None,
                "name": run.name,
                "status": run.status,
                "started_at": timestamp(run.started_at),
                "ended_at": timestamp(run.ended_at),
                "agent": agents_by_id[run.agent_id].slug if run.agent_id in agents_by_id else None,
                "version": (
                    versions_by_id[run.agent_version_id].version
                    if run.agent_version_id in versions_by_id
                    else None
                ),
                "attributes": run.attributes,
            }
            for run in agent_runs
        ],
        "errors": [
            {
                "id": str(error.id),
                "type": error.type,
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
                "retry_count": error.retry_count,
                "event_id": str(error.event_id) if error.event_id else None,
                "span_id": str(error.span_id) if error.span_id else None,
                "created_at": timestamp(error.created_at),
            }
            for error in errors
        ],
        "usage": [
            {
                "provider": item.provider,
                "model": item.model,
                "input_tokens": item.input_tokens,
                "output_tokens": item.output_tokens,
                "total_tokens": item.total_tokens,
                "audio_seconds": json_number(item.audio_seconds),
                "tts_characters": item.tts_characters,
            }
            for item in usage
        ],
        "costs": [
            {
                "amount_micros": item.amount_micros,
                "currency": item.currency,
                "source": item.source,
                "is_estimate": item.is_estimate,
                "rate_card_version": item.rate_card_version,
                "span_id": str(item.span_id) if item.span_id else None,
            }
            for item in costs
        ],
        "findings": [
            {
                **{
                    "id": str(finding.id),
                    "type": finding.type,
                    "certainty": finding.certainty,
                    "severity": finding.severity,
                    "statement": finding.statement,
                    "confidence": json_number(finding.confidence),
                    "rule_id": finding.rule_id,
                    "rule_version": finding.rule_version,
                    "attributes": finding.attributes,
                    "created_at": timestamp(finding.created_at),
                },
                "evidence": [
                    evidence_target(evidence)
                    for evidence in db.scalars(
                        select(FindingEvidence).where(FindingEvidence.finding_id == finding.id)
                    )
                ],
            }
            for finding in findings
        ],
        "analysis_runs": [
            {
                "id": str(run.id),
                "status": run.status,
                "analysis_version": run.analysis_version,
                "prompt_version": run.prompt_version,
                "model": run.model,
                "schema_version": run.schema_version,
                "evaluator_latency_ms": json_number(run.evaluator_latency_ms),
                "input_tokens": run.input_tokens,
                "output_tokens": run.output_tokens,
                "cost_micros": run.cost_micros,
                "result": run.result,
                "error": run.error,
                "started_at": timestamp(run.started_at),
                "completed_at": timestamp(run.completed_at),
                "created_at": timestamp(run.created_at),
            }
            for run in analysis_runs
        ],
        "recordings": [
            {
                "id": str(recording.id),
                "source": recording.source,
                "external_id": recording.external_id,
                "duration_ms": recording.duration_ms,
                "media_type": recording.media_type,
                "status": recording.status,
                "expires_at": timestamp(recording.expires_at),
            }
            for recording in recordings
        ],
    }


@router.post("/projects/{project_slug}/sessions/{session_id}/analysis")
def request_reanalysis(
    project_slug: str, session_id: UUID, db: Session = Depends(get_db)
) -> dict[str, str]:
    """Queue a new deterministic and semantic pass without mutating prior analysis runs."""

    project = project_for_slug(db, project_slug)
    session = db.scalar(
        select(VoiceSession).where(
            VoiceSession.project_id == project.id, VoiceSession.id == session_id
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    for job_type in ("run_deterministic_analysis", "run_semantic_analysis"):
        prompt_prefix = "deterministic" if job_type == "run_deterministic_analysis" else "semantic"
        latest_version = db.scalar(
            select(func.max(AnalysisRun.analysis_version)).where(
                AnalysisRun.session_id == session.id,
                AnalysisRun.prompt_version.like(f"{prompt_prefix}-%"),
            )
        )
        analysis_run = AnalysisRun(
            session_id=session.id,
            status="queued",
            analysis_version=int(latest_version or 0) + 1,
            prompt_version=f"{prompt_prefix}-v2",
            schema_version="2",
        )
        db.add(analysis_run)
        db.flush()
        db.add(
            Job(
                project_id=project.id,
                type=job_type,
                payload={
                    "session_id": str(session.id),
                    "analysis_run_id": str(analysis_run.id),
                    "trigger": "manual_reanalysis",
                },
            )
        )
    db.commit()
    return {"status": "queued"}


@router.post("/projects/{project_slug}/sessions/{session_id}/recordings", status_code=201)
def attach_recording_metadata(
    project_slug: str,
    session_id: UUID,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, str | None]:
    """Attach optional external/private recording metadata without copying audio."""

    project = project_for_slug(db, project_slug)
    session = db.scalar(
        select(VoiceSession).where(
            VoiceSession.project_id == project.id, VoiceSession.id == session_id
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    source = payload.get("source")
    if not isinstance(source, str) or not source:
        raise HTTPException(status_code=422, detail="recording source is required")
    duration_ms = payload.get("duration_ms")
    if duration_ms is not None and (not isinstance(duration_ms, int) or duration_ms < 0):
        raise HTTPException(status_code=422, detail="duration_ms must be a non-negative integer")
    external_id = payload.get("external_id")
    asset_reference = payload.get("asset_reference")
    media_type = payload.get("media_type")
    recording_status = payload.get("status")
    status_value = recording_status if isinstance(recording_status, str) else "available"
    asset_value = asset_reference if isinstance(asset_reference, str) else None
    try:
        validate_recording_metadata(
            source=source,
            status=status_value,
            asset_reference=asset_value,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    expires_at = payload.get("expires_at")
    parsed_expiry: datetime | None = None
    if isinstance(expires_at, str):
        try:
            parsed_expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise HTTPException(status_code=422, detail="expires_at must be ISO-8601") from error
    elif isinstance(expires_at, datetime):
        parsed_expiry = expires_at
    recording = Recording(
        session_id=session.id,
        source=source,
        external_id=external_id if isinstance(external_id, str) else None,
        asset_reference=(
            None if status_value in {"deleted", "expired", "denied", "unavailable"} else asset_value
        ),
        duration_ms=duration_ms,
        media_type=media_type if isinstance(media_type, str) else None,
        status=status_value,
        expires_at=recording_expiry(parsed_expiry, get_settings()),
    )
    db.add(recording)
    db.commit()
    return {
        "id": str(recording.id),
        "status": recording.status,
        "expires_at": timestamp(recording.expires_at),
    }


@router.delete("/projects/{project_slug}/sessions/{session_id}/recordings/{recording_id}")
def delete_recording_metadata(
    project_slug: str,
    session_id: UUID,
    recording_id: UUID,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Revoke optional recording access without deleting canonical trace data."""

    project = project_for_slug(db, project_slug)
    recording = db.scalar(
        select(Recording)
        .join(VoiceSession, Recording.session_id == VoiceSession.id)
        .where(
            VoiceSession.project_id == project.id,
            VoiceSession.id == session_id,
            Recording.id == recording_id,
        )
    )
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    recording.asset_reference = None
    recording.status = "deleted"
    db.commit()
    return {"id": str(recording.id), "status": recording.status}


@router.get(
    "/projects/{project_slug}/sessions/{session_id}/recordings/{recording_id}/playback",
    response_model=None,
)
def redirect_to_recording_playback(
    project_slug: str,
    session_id: UUID,
    recording_id: UUID,
    db: Session = Depends(get_db),
) -> RedirectResponse | FileResponse:
    """Issue playback through a short-lived signed URL; audio never transits this API."""

    project = project_for_slug(db, project_slug)
    recording = db.scalar(
        select(Recording)
        .join(VoiceSession, Recording.session_id == VoiceSession.id)
        .where(
            VoiceSession.project_id == project.id,
            VoiceSession.id == session_id,
            Recording.id == recording_id,
        )
    )
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    if recording.expires_at is not None:
        expiry = (
            recording.expires_at.replace(tzinfo=UTC)
            if recording.expires_at.tzinfo is None
            else recording.expires_at.astimezone(UTC)
        )
        if expiry <= datetime.now(UTC):
            recording.asset_reference = None
            recording.status = "expired"
            db.commit()
    if recording.status != "available":
        raise HTTPException(status_code=410, detail="Recording is no longer available")
    # Development seed recordings intentionally use a repository fixture. This
    # path is unavailable outside development and is constrained to the repo.
    if recording.source == "local":
        if get_settings().app_env != "development" or not recording.asset_reference:
            raise HTTPException(status_code=404, detail="Local demo recording is unavailable")
        path = (REPOSITORY_ROOT / recording.asset_reference).resolve()
        if REPOSITORY_ROOT not in path.parents or not path.is_file():
            raise HTTPException(status_code=404, detail="Local demo recording was not found")
        return FileResponse(path, media_type=recording.media_type or "audio/mpeg")
    try:
        url = (
            external_playback_url(recording)
            if recording.source in {"vapi", "retell", "external"}
            else cloudinary_playback_url(recording, get_settings())
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return RedirectResponse(url=url, status_code=307)
