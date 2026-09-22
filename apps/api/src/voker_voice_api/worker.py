import os
import socket
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from voker_voice_api.analysis import run_deterministic_analysis
from voker_voice_api.connectors import normalize_retell, normalize_vapi
from voker_voice_api.database import SessionLocal
from voker_voice_api.ingestion import IngestContext, ingest_batch
from voker_voice_api.jobs import claim_jobs, complete_job, fail_job, release_expired_leases
from voker_voice_api.models import (
    Environment,
    Integration,
    Job,
    Recording,
    WebhookDelivery,
    WebhookReceipt,
)
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
        jobs = claim_jobs(db, worker_id=identifier, limit=limit)
        job_ids = [job.id for job in jobs]
    processed = 0
    for job_id in job_ids:
        with SessionLocal.begin() as db:
            job = db.get(Job, job_id)
            if job is None or job.state != "running" or job.locked_by != identifier:
                continue
            try:
                process_job(db, job)
                complete_job(job)
                processed += 1
            except Exception as error:
                fail_job(job, error=str(error))
    return processed
