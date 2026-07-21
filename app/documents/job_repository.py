from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.documents.jobs import ParseJob, ParseJobStatus, transition_job


class ParseJobRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, job: ParseJob) -> ParseJob:
        self.session.add(job)
        self.session.flush()
        return job

    def get(self, job_id: str, *, lock: bool = False) -> ParseJob | None:
        statement = select(ParseJob).where(ParseJob.id == job_id)
        if lock:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def for_version(self, version_id: str) -> ParseJob | None:
        return self.session.scalar(
            select(ParseJob).where(ParseJob.document_version_id == version_id)
        )

    def transition(
        self,
        job_id: str,
        target: ParseJobStatus,
        *,
        error_code: str | None = None,
        worker_id: str | None = None,
    ) -> ParseJob:
        job = self.get(job_id, lock=True)
        if job is None:
            raise ValueError("parse job not found")
        transition_job(job.status, target)
        now = datetime.now(timezone.utc)
        job.status = target
        job.updated_at = now
        job.error_code = error_code
        if worker_id:
            job.worker_id = worker_id
        if target == ParseJobStatus.SCANNING:
            job.started_at = now
            job.attempt_count += 1
        if target in {
            ParseJobStatus.READY_FOR_REVIEW,
            ParseJobStatus.INFECTED,
            ParseJobStatus.FAILED,
        }:
            job.completed_at = now
        self.session.commit()
        return job
