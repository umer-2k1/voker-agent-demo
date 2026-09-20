from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from voker_voice_api.models import Job

JobFailureState = Literal["retry", "dead"]


def claim_jobs(
    db: Session, *, worker_id: str, limit: int = 10, now: datetime | None = None
) -> list[Job]:
    """Lease due work transactionally so multiple workers cannot process the same row."""

    claimed_at = now or datetime.now(UTC)
    jobs = list(
        db.scalars(
            select(Job)
            .where(Job.state.in_(("pending", "retry")), Job.scheduled_at <= claimed_at)
            .order_by(Job.scheduled_at, Job.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    for job in jobs:
        job.state = "running"
        job.locked_at = claimed_at
        job.locked_by = worker_id
        job.attempt_count += 1
    return jobs


def complete_job(job: Job) -> None:
    job.state = "completed"
    job.locked_at = None
    job.locked_by = None
    job.last_error = None


def fail_job(
    job: Job,
    *,
    error: str,
    now: datetime | None = None,
    retry_delay: timedelta = timedelta(seconds=30),
) -> JobFailureState:
    job.last_error = error[:10_000]
    job.locked_at = None
    job.locked_by = None
    if job.attempt_count >= job.max_attempts:
        job.state = "dead"
        return "dead"
    job.state = "retry"
    job.scheduled_at = (now or datetime.now(UTC)) + retry_delay
    return "retry"


def release_expired_leases(
    db: Session,
    *,
    now: datetime | None = None,
    lease_timeout: timedelta = timedelta(minutes=5),
) -> int:
    """Return abandoned worker leases to retryable state after a process restart."""

    current = now or datetime.now(UTC)
    expired_before = current - lease_timeout
    jobs = list(
        db.scalars(
            select(Job)
            .where(
                Job.state == "running", Job.locked_at.is_not(None), Job.locked_at < expired_before
            )
            .with_for_update(skip_locked=True)
        )
    )
    for job in jobs:
        job.state = "retry"
        job.locked_at = None
        job.locked_by = None
        job.scheduled_at = current
    return len(jobs)
