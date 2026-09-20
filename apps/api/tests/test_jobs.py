from datetime import UTC, datetime, timedelta

from voker_voice_api.jobs import complete_job, fail_job
from voker_voice_api.models import Job


def test_complete_job_clears_lease() -> None:
    job = Job(type="analysis", state="running", payload={}, attempt_count=1, max_attempts=3)
    job.locked_at = datetime.now(UTC)
    job.locked_by = "worker-1"

    complete_job(job)

    assert job.state == "completed"
    assert job.locked_at is None
    assert job.locked_by is None


def test_failed_job_is_retried_before_dead_letter() -> None:
    now = datetime.now(UTC)
    job = Job(type="analysis", state="running", payload={}, attempt_count=1, max_attempts=3)

    state = fail_job(job, error="temporary failure", now=now, retry_delay=timedelta(seconds=5))

    assert state == "retry"
    assert job.state == "retry"
    assert job.scheduled_at == now + timedelta(seconds=5)


def test_failed_job_becomes_dead_at_attempt_limit() -> None:
    job = Job(type="analysis", state="running", payload={}, attempt_count=3, max_attempts=3)

    state = fail_job(job, error="permanent failure")

    assert state == "dead"
    assert job.state == "dead"
