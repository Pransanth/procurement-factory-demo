"""Background job: remind approvers about procurement requests that have
been sitting in 'submitted' status too long.

Like every job handler in app/jobs/, this receives a ScopedRepositories
instance already bound to the job's own organization (see
app/jobs/scoped_repositories.py and app/jobs/queue.py). It never imports
app.repositories.* directly and has no parameter through which it could
address a different organization.
"""

from datetime import datetime, timedelta, timezone

from app.jobs.handlers import register

JOB_TYPE = "approval_reminder"
DEFAULT_OLDER_THAN_HOURS = 24


def _now():
    return datetime.now(timezone.utc).isoformat()


def _hours_before(now_iso, hours):
    now_dt = datetime.fromisoformat(now_iso)
    return (now_dt - timedelta(hours=hours)).isoformat()


def handle(scope, payload):
    older_than_hours = payload.get("older_than_hours", DEFAULT_OLDER_THAN_HOURS)
    now = payload.get("now") or _now()
    cutoff = _hours_before(now, older_than_hours)

    pending = scope.list_pending_procurement_requests_older_than(cutoff)
    for request in pending:
        scope.record_audit_log(
            action="approval_reminder.sent",
            entity_type="procurement_request",
            entity_id=request.id,
            details={"amount_cents": request.amount_cents},
            now=now,
        )

    return {"reminded_count": len(pending), "request_ids": [r.id for r in pending]}


register(JOB_TYPE, handle)
