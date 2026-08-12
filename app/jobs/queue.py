"""A deliberately simple in-process background job queue.

`enqueue` stores organization_id both as a queue-level column (cheap to
query, e.g. "all pending jobs for org X") and inside the JSON payload
itself — the payload copy is the one that matters, because that's what a
handler actually receives.

`run_pending` processes ALL due jobs across ALL organizations in one pass,
the way a real worker process would: it is not scoped to any single tenant.
For each job it looks up the handler by job_type and calls
`handler(conn, payload)`. There is no shared "current organization" context
object, thread-local, or connection-level filter injected here — a handler
gets exactly its own payload and is on its own to use the organization_id
inside it correctly. That absence is intentional: see app/jobs/handlers.py.
"""

import json
from datetime import datetime, timezone

from app.jobs.handlers import HANDLERS
from app.models import Job


def _now():
    return datetime.now(timezone.utc).isoformat()


def _row_to_job(row):
    return Job(
        id=row["id"],
        organization_id=row["organization_id"],
        job_type=row["job_type"],
        payload=row["payload"],
        status=row["status"],
        scheduled_for=row["scheduled_for"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        result=row["result"],
        error=row["error"],
    )


def enqueue(conn, job_type, organization_id, payload=None, scheduled_for=None, now=None):
    created_at = now or _now()
    payload_dict = dict(payload or {})
    payload_dict["organization_id"] = organization_id

    cursor = conn.execute(
        "INSERT INTO jobs (organization_id, job_type, payload, status, scheduled_for, created_at) "
        "VALUES (?, ?, ?, 'pending', ?, ?)",
        (organization_id, job_type, json.dumps(payload_dict), scheduled_for, created_at),
    )
    conn.commit()
    return cursor.lastrowid


def get_by_id(conn, job_id):
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row else None


def run_pending(conn, handlers=None, now=None):
    """Run all due pending jobs. Returns a list of {job_id, status} dicts."""
    handlers = HANDLERS if handlers is None else handlers
    run_at = now or _now()

    rows = conn.execute(
        "SELECT * FROM jobs WHERE status = 'pending' AND (scheduled_for IS NULL OR scheduled_for <= ?) "
        "ORDER BY id",
        (run_at,),
    ).fetchall()

    results = []
    for row in rows:
        job_id = row["id"]
        job_type = row["job_type"]
        payload = json.loads(row["payload"])

        conn.execute(
            "UPDATE jobs SET status = 'running', started_at = ? WHERE id = ?", (run_at, job_id)
        )
        conn.commit()

        handler = handlers.get(job_type)
        if handler is None:
            _finish(conn, job_id, "failed", run_at, error=f"no handler registered for job_type '{job_type}'")
            results.append({"job_id": job_id, "status": "failed"})
            continue

        try:
            result = handler(conn, payload)
        except Exception as exc:
            _finish(conn, job_id, "failed", run_at, error=str(exc))
            results.append({"job_id": job_id, "status": "failed"})
            continue

        _finish(conn, job_id, "succeeded", run_at, result=result)
        results.append({"job_id": job_id, "status": "succeeded"})

    return results


def _finish(conn, job_id, status, finished_at, result=None, error=None):
    conn.execute(
        "UPDATE jobs SET status = ?, finished_at = ?, result = ?, error = ? WHERE id = ?",
        (status, finished_at, json.dumps(result) if result is not None else None, error, job_id),
    )
    conn.commit()
