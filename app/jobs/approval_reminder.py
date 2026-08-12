"""Background job: remind approvers about procurement requests that have
been sitting in 'submitted' status too long.

Like every job handler in app/jobs/, this reads organization_id from its
own payload (see app/jobs/queue.py) and threads it through to every
repository call it makes. Nothing outside this function enforces that it
does so correctly.
"""

from datetime import datetime, timedelta, timezone

from app.jobs.handlers import register
from app.repositories import audit_log, procurement_requests

JOB_TYPE = "approval_reminder"
DEFAULT_OLDER_THAN_HOURS = 24


def _now():
    return datetime.now(timezone.utc).isoformat()


def _hours_before(now_iso, hours):
    now_dt = datetime.fromisoformat(now_iso)
    return (now_dt - timedelta(hours=hours)).isoformat()


def handle(conn, payload):
    organization_id = payload["organization_id"]
    older_than_hours = payload.get("older_than_hours", DEFAULT_OLDER_THAN_HOURS)
    now = payload.get("now") or _now()
    cutoff = _hours_before(now, older_than_hours)

    pending = procurement_requests.list_pending_older_than(conn, organization_id, cutoff)
    for request in pending:
        audit_log.record(
            conn,
            organization_id,
            action="approval_reminder.sent",
            entity_type="procurement_request",
            entity_id=request.id,
            details={"amount_cents": request.amount_cents},
            now=now,
        )

    return {"reminded_count": len(pending), "request_ids": [r.id for r in pending]}


register(JOB_TYPE, handle)
