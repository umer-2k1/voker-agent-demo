import os
import socket
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from voker_voice_api.analysis import run_deterministic_analysis
from voker_voice_api.config import get_settings
from voker_voice_api.connectors import normalize_retell, normalize_vapi
from voker_voice_api.database import SessionLocal
from voker_voice_api.ingestion import IngestContext, enqueue_completion_analysis, ingest_batch
from voker_voice_api.jobs import claim_jobs, complete_job, fail_job, release_expired_leases
from voker_voice_api.models import (
    Environment,
    Integration,
    Job,
    Recording,
    Event,
    Session as VoiceSession,
    WebhookDelivery,
    WebhookReceipt,
)
from voker_voice_api.session_logs import write_session_log
from voker_voice_api.semantic import evaluate_session


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def expire_recordings(db: Session, *, now: datetime | None = None) -> int:
    """Revoke expired recording references while retaining the session trace."""

    current = now or datetime.now(UTC)
    recordings = list(
        db.scalars(
            select(Recording).where(
                Recording.expires_at.is_not(None),
                Recording.expires_at <= current,
                Recording.status.not_in(("deleted", "expired")),
            )
        )
    )
    for recording in recordings:
        recording.asset_reference = None
        recording.status = "expired"
    return len(recordings)


def reconcile_stale_sessions(
    db: Session, *, now: datetime | None = None, session_id: uuid.UUID | None = None
) -> int:
    """Finalize stalled traces when an SDK/process misses its terminal event.

    This is a safety net, never a claim that the call completed successfully:
    the session is marked ``incomplete`` and analyses are still queued against
    the evidence that was actually persisted.
    """

    current = now or datetime.now(UTC)
    cutoff = current - timedelta(seconds=get_settings().session_stale_after_seconds)
    latest_event = (
        select(Event.session_id.label("session_id"), func.max(Event.received_at).label("received_at"))
        .group_by(Event.session_id)
        .subquery()
    )
    conditions = [
        VoiceSession.status == "in_progress",
        func.coalesce(latest_event.c.received_at, VoiceSession.started_at) <= cutoff,
    ]
    if session_id is not None:
        conditions.append(VoiceSession.id == session_id)
    sessions = list(
        db.scalars(
            select(VoiceSession)
            .outerjoin(latest_event, latest_event.c.session_id == VoiceSession.id)
            .where(*conditions)
            # Postgres cannot lock the grouped latest-event subquery. Lock only
            # the mutable session rows, which is the resource being reconciled.
            .with_for_update(of=VoiceSession, skip_locked=True)
        )
    )
    for session in sessions:
        last_event_at = db.scalar(
            select(func.max(Event.occurred_at)).where(Event.session_id == session.id)
        )
        session.status = "incomplete"
        session.ended_at = last_event_at or session.started_at
        enqueue_completion_analysis(db, session.project_id, session.id)
        write_session_log(
            str(session.id),
            "stale_session_reconciled",
            {
                "reason": "terminal_event_missing_after_inactivity",
                "last_event_at": last_event_at.isoformat() if last_event_at else None,
                "stale_after_seconds": get_settings().session_stale_after_seconds,
            },
            external_session_id=session.external_session_id,
        )
    return len(sessions)


def process_job(db: Session, job: Job) -> None:
    if job.type == "run_deterministic_analysis":
        session_value = job.payload.get("session_id")
        if not isinstance(session_value, str):
            raise ValueError("run_deterministic_analysis job requires session_id")
        run_value = job.payload.get("analysis_run_id")
        run_deterministic_analysis(
            db,
            session_id=uuid.UUID(session_value),
            analysis_run_id=uuid.UUID(run_value) if isinstance(run_value, str) else None,
        )
        return
    if job.type == "run_semantic_analysis":
        session_value = job.payload.get("session_id")
        if not isinstance(session_value, str):
            raise ValueError("run_semantic_analysis job requires session_id")
        run_value = job.payload.get("analysis_run_id")
        evaluate_session(
            db,
            session_id=uuid.UUID(session_value),
            analysis_run_id=uuid.UUID(run_value) if isinstance(run_value, str) else None,
        )
        return
    if job.type == "normalize_webhook":
        receipt_value = job.payload.get("receipt_id")
        if not isinstance(receipt_value, str):
            raise ValueError("normalize_webhook job requires receipt_id")
        receipt = db.get(WebhookReceipt, uuid.UUID(receipt_value))
        if receipt is None or receipt.processed_at is not None:
            return
        integration = db.get(Integration, receipt.integration_id)
        if integration is None:
            raise ValueError("webhook integration no longer exists")
        environment_id = integration.config.get("environment_id")
        environment = (
            db.get(Environment, uuid.UUID(environment_id))
            if isinstance(environment_id, str)
            else db.scalar(
                select(Environment)
                .where(Environment.project_id == integration.project_id)
                .order_by(Environment.created_at)
            )
        )
        if environment is None:
            raise ValueError("integration project has no environment")
        events = (
            normalize_vapi(receipt.payload, receipt.provider_delivery_id, integration.config)
            if integration.provider == "vapi"
            else normalize_retell(receipt.payload, receipt.provider_delivery_id, integration.config)
        )
        ingest_batch(
            db,
            IngestContext(
                resolved_project_id=integration.project_id,
                resolved_environment_id=environment.id,
            ),
            events,
        )
        receipt.processed_at = datetime.now(UTC)
        return
    if job.type == "forward_webhook":
        delivery_value = job.payload.get("delivery_id")
        if not isinstance(delivery_value, str):
            raise ValueError("forward_webhook job requires delivery_id")
        delivery = db.get(WebhookDelivery, uuid.UUID(delivery_value))
        if delivery is None or delivery.status in {"succeeded", "disabled"}:
            return
        integration = db.get(Integration, delivery.integration_id)
        if (
            integration is None
            or integration.status == "disabled"
            or not integration.config.get("forwarding_enabled", True)
        ):
            delivery.status = "disabled"
            return
        receipt = db.get(WebhookReceipt, delivery.receipt_id) if delivery.receipt_id else None
        if receipt is None:
            raise ValueError("forwarding receipt no longer exists")
        delivery.attempt_count += 1
        try:
            response = httpx.post(delivery.destination_url, json=receipt.payload, timeout=10.0)
            response.raise_for_status()
        except httpx.HTTPError as error:
            delivery.last_error = str(error)[:10_000]
            delivery.status = "failed" if job.attempt_count >= job.max_attempts else "retry"
            raise
        delivery.status = "succeeded"
        delivery.last_error = None
        delivery.next_attempt_at = None
        return
    raise ValueError(f"Unsupported job type: {job.type}")


def run_once(*, limit: int = 10) -> int:
    identifier = worker_id()
    with SessionLocal.begin() as db:
        release_expired_leases(db)
        reconcile_stale_sessions(db)
        jobs = claim_jobs(db, worker_id=identifier, limit=limit)
        job_ids = [job.id for job in jobs]
    processed = 0
    for job_id in job_ids:
        with SessionLocal.begin() as db:
            job = db.get(Job, job_id)
            if job is None or job.state != "running" or job.locked_by != identifier:
                continue
            try:
                session_value = job.payload.get("session_id")
                if isinstance(session_value, str):
                    write_session_log(
                        session_value,
                        "worker_job_started",
                        {"job_id": str(job.id), "job_type": job.type, "attempt": job.attempt_count},
                    )
                process_job(db, job)
                complete_job(job)
                if isinstance(session_value, str):
                    write_session_log(
                        session_value,
                        "worker_job_completed",
                        {"job_id": str(job.id), "job_type": job.type},
                    )
                processed += 1
            except Exception as error:
                fail_job(job, error=str(error))
                session_value = job.payload.get("session_id")
                if isinstance(session_value, str):
                    write_session_log(
                        session_value,
                        "worker_job_failed",
                        {"job_id": str(job.id), "job_type": job.type, "error": str(error)},
                    )
    return processed
