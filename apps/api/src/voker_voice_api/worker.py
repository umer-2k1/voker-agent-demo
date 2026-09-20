import os
import socket

from sqlalchemy.orm import Session

from voker_voice_api.analysis import run_deterministic_analysis
from voker_voice_api.database import SessionLocal
from voker_voice_api.jobs import claim_jobs, complete_job, fail_job, release_expired_leases
from voker_voice_api.models import Job


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def process_job(db: Session, job: Job) -> None:
    if job.type == "run_deterministic_analysis":
        session_value = job.payload.get("session_id")
        if not isinstance(session_value, str):
            raise ValueError("run_deterministic_analysis job requires session_id")
        import uuid

        run_deterministic_analysis(db, session_id=uuid.UUID(session_value))
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
