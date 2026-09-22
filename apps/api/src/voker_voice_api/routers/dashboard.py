import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from voker_voice_api.analytics import CohortValue, latency_distribution, voice_impact_cohorts
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
from voker_voice_api.recordings import cloudinary_playback_url
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
def analytics_overview(project_slug: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Bounded project aggregates that retain unknown costs/metrics as unknown."""

    project = project_for_slug(db, project_slug)
    sessions = list(db.scalars(select(VoiceSession).where(VoiceSession.project_id == project.id)))
    completed = [item for item in sessions if item.status == "completed"]
    outcome_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for item in sessions:
        source_counts[item.source] = source_counts.get(item.source, 0) + 1
        if item.outcome:
            outcome_counts[item.outcome] = outcome_counts.get(item.outcome, 0) + 1
    costs = list(
        db.scalars(
            select(CostRecord)
            .join(VoiceSession, CostRecord.session_id == VoiceSession.id)
            .where(VoiceSession.project_id == project.id)
        )
    )
    events_by_session: dict[object, list[Event]] = {item.id: [] for item in sessions}
    if sessions:
        events = db.scalars(select(Event).where(Event.session_id.in_(events_by_session))).all()
        for event in events:
            events_by_session[event.session_id].append(event)
    cohort_values = []
    for item in sessions:
        events = events_by_session[item.id]
        stt_durations = [
            float(event.duration_ms)
            for event in events
            if event.event_type == "stt.completed" and event.duration_ms is not None
        ]
        cohort_values.append(
            CohortValue(
                key=str(item.id),
                outcome=item.outcome,
                interruption_count=sum(
                    event.event_type == "voice.interruption" for event in events
                ),
                stt_duration_ms=max(stt_durations) if stt_durations else None,
            )
        )
    spans_by_kind: dict[str, list[float]] = {"stt": [], "llm": [], "tool": [], "tts": []}
    tool_failure_sessions: set[UUID] = set()
    if sessions:
        spans = db.scalars(
            select(Span).where(Span.session_id.in_(events_by_session)).limit(5000)
        ).all()
        for span in spans:
            if span.kind in spans_by_kind and span.duration_ms is not None:
                spans_by_kind[span.kind].append(float(span.duration_ms))
            if span.kind in {"tool", "mcp"} and span.status in {
                "error",
                "failed",
                "timeout",
                "cancelled",
            }:
                tool_failure_sessions.add(span.session_id)
    correction_sessions = {
        event.session_id
        for events in events_by_session.values()
        for event in events
        if event.event_type.startswith("correction.")
    }
    abandonment_sessions = {
        event.session_id
        for events in events_by_session.values()
        for event in events
        if event.event_type.startswith("abandonment.")
    }
    error_sessions = set(
        db.scalars(
            select(Error.session_id)
            .join(VoiceSession, Error.session_id == VoiceSession.id)
            .where(VoiceSession.project_id == project.id)
            .distinct()
        )
    )
    failure_categories: dict[str, int] = {}
    failure_category_sessions: dict[str, set[UUID]] = {}
    findings = db.scalars(
        select(Finding)
        .join(VoiceSession, Finding.session_id == VoiceSession.id)
        .where(VoiceSession.project_id == project.id)
        .limit(1000)
    ).all()
    for finding in findings:
        category = finding.attributes.get("failure_category") or finding.type
        if isinstance(category, str):
            failure_categories[category] = failure_categories.get(category, 0) + 1
            failure_category_sessions.setdefault(category, set()).add(finding.session_id)

    known_outcomes = [item for item in sessions if item.outcome]
    resolved_sessions = {item.id for item in sessions if item.outcome == "success"}
    escalated_sessions = {item.id for item in sessions if item.outcome == "escalated"}
    abandoned_sessions = {
        item.id for item in sessions if item.outcome == "abandoned"
    } | abandonment_sessions
    agent_comparison: dict[str, dict[str, Any]] = {}
    for item in sessions:
        agent = db.get(Agent, item.agent_id) if item.agent_id else None
        version = db.get(AgentVersion, item.agent_version_id) if item.agent_version_id else None
        label = " · ".join(
            value
            for value in (
                agent.slug if agent else "Unknown agent",
                version.version if version else None,
            )
            if value
        )
        group = agent_comparison.setdefault(label, {"sessions": 0, "resolved": 0})
        group["sessions"] += 1
        group["resolved"] += item.outcome == "success"
    provider_comparison: dict[str, dict[str, Any]] = {}
    usage_rows = db.scalars(
        select(UsageRecord)
        .join(VoiceSession, UsageRecord.session_id == VoiceSession.id)
        .where(VoiceSession.project_id == project.id)
        .limit(5000)
    ).all()
    sessions_by_id = {item.id: item for item in sessions}
    provider_session_keys: set[tuple[str, UUID]] = set()
    for usage_row in usage_rows:
        label = " · ".join(
            value for value in (usage_row.provider or "Unknown provider", usage_row.model) if value
        )
        key = (label, usage_row.session_id)
        if key in provider_session_keys:
            continue
        provider_session_keys.add(key)
        group = provider_comparison.setdefault(label, {"sessions": 0, "resolved": 0})
        group["sessions"] += 1
        group["resolved"] += sessions_by_id[usage_row.session_id].outcome == "success"

    def rate(session_ids: set[UUID], denominator: int | None = None) -> float | None:
        size = denominator if denominator is not None else len(sessions)
        return len(session_ids) / size if size else None

    def session_links(session_ids: set[UUID]) -> list[str]:
        return [str(session_id) for session_id in list(session_ids)[:10]]

    return {
        "session_count": len(sessions),
        "completed_session_count": len(completed),
        "outcomes": outcome_counts,
        "sources": source_counts,
        "cost": {
            "amount_micros": sum(item.amount_micros for item in costs) if costs else None,
            "currency": "USD" if costs else None,
            "record_count": len(costs),
            "estimated_record_count": sum(1 for item in costs if item.is_estimate),
        },
        "voice_impact_cohorts": voice_impact_cohorts(cohort_values),
        "latency": {kind: latency_distribution(values) for kind, values in spans_by_kind.items()},
        "rates": {
            "resolution": rate(resolved_sessions, len(known_outcomes)),
            "correction": rate(correction_sessions),
            "escalation": rate(escalated_sessions),
            "abandonment": rate(abandoned_sessions),
            "error": rate(error_sessions),
        },
        "failure_categories": dict(
            sorted(failure_categories.items(), key=lambda item: item[1], reverse=True)[:8]
        ),
        "failure_category_insights": [
            {
                "category": category,
                "count": count,
                "session_ids": session_links(failure_category_sessions[category]),
            }
            for category, count in sorted(
                failure_categories.items(), key=lambda item: item[1], reverse=True
            )[:8]
        ],
        "tool_failure_count": len(tool_failure_sessions),
        "insights": [
            {
                "key": "errors",
                "label": "Sessions with recorded errors",
                "count": len(error_sessions),
                "session_ids": session_links(error_sessions),
            },
            {
                "key": "tool_failures",
                "label": "Sessions with failed tools",
                "count": len(tool_failure_sessions),
                "session_ids": session_links(tool_failure_sessions),
            },
            {
                "key": "corrections",
                "label": "Sessions with observed corrections",
                "count": len(correction_sessions),
                "session_ids": session_links(correction_sessions),
            },
            {
                "key": "abandonment",
                "label": "Sessions with observed abandonment",
                "count": len(abandoned_sessions),
                "session_ids": session_links(abandoned_sessions),
            },
        ],
        "comparisons": {
            "agents": [
                {
                    "label": label,
                    **values,
                    "resolution_rate": values["resolved"] / values["sessions"],
                }
                for label, values in agent_comparison.items()
            ],
            "providers": [
                {
                    "label": label,
                    **values,
                    "resolution_rate": values["resolved"] / values["sessions"],
                }
                for label, values in provider_comparison.items()
            ],
        },
        "outcome_sources": {
            "explicit": sum(item.outcome_source == "explicit" for item in sessions),
            "inferred": sum(item.outcome_source == "semantic" for item in sessions),
            "unknown": sum(not item.outcome_source for item in sessions),
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
) -> dict[str, str]:
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
    recording = Recording(
        session_id=session.id,
        source=source,
        external_id=external_id if isinstance(external_id, str) else None,
        asset_reference=asset_reference if isinstance(asset_reference, str) else None,
        duration_ms=duration_ms,
        media_type=media_type if isinstance(media_type, str) else None,
        status=recording_status if isinstance(recording_status, str) else "available",
    )
    db.add(recording)
    db.commit()
    return {"id": str(recording.id), "status": recording.status}


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
        url = cloudinary_playback_url(recording, get_settings())
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return RedirectResponse(url=url, status_code=307)
