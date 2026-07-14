from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from app.db.session import is_enabled, session_scope
from app.models import CrawlJob


def start_job(job_type: str, target_count: int = 0, details: Optional[dict] = None) -> Optional[int]:
    if not is_enabled():
        return None
    with session_scope() as session:
        job = CrawlJob(
            job_type=job_type,
            status="running",
            target_count=target_count,
            details=details or {},
        )
        session.add(job)
        session.flush()
        return int(job.id)


def finish_job(
    job_id: Optional[int],
    *,
    status: str,
    success_count: int = 0,
    failed_count: int = 0,
    started_monotonic: Optional[float] = None,
    details: Optional[dict] = None,
    error: str = "",
) -> Optional[bool]:
    if not job_id or not is_enabled():
        return None

    with session_scope() as session:
        job = session.execute(select(CrawlJob).where(CrawlJob.id == job_id)).scalar_one_or_none()
        if job is None:
            return False
        job.status = status
        job.success_count = success_count
        job.failed_count = failed_count
        job.duration_seconds = time.monotonic() - started_monotonic if started_monotonic else None
        job.details = {**(job.details or {}), **(details or {})}
        job.error = error or None
        job.finished_at = datetime.now(timezone.utc)
        return True
