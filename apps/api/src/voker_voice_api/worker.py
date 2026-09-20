import os
import socket
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from voker_voice_api.analysis import run_deterministic_analysis
from voker_voice_api.connectors import normalize_retell, normalize_vapi
from voker_voice_api.database import SessionLocal
from voker_voice_api.ingestion import IngestContext, ingest_batch
from voker_voice_api.jobs import claim_jobs, complete_job, fail_job, release_expired_leases
from voker_voice_api.models import Environment, Integration, Job, Recording, WebhookReceipt
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
        run_deterministic_analysis(db, session_id=uuid.UUID(session_value))
        return
    if job.type == "run_semantic_analysis":
        session_value = job.payload.get("session_id")
        if not isinstance(session_value, str):
            raise ValueError("run_semantic_analysis job requires session_id")
        evaluate_session(db, session_id=uuid.UUID(session_value))
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
        environment = db.scalar(
            select(Environment)
            .where(Environment.project_id == integration.project_id)
            .order_by(Environment.created_at)
        )
        if environment is None:
            raise ValueError("integration project has no environment")
        events = (
            normalize_vapi(receipt.payload, receipt.provider_delivery_id)
            if integration.provider == "vapi"
            else normalize_retell(receipt.payload, receipt.provider_delivery_id)
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
