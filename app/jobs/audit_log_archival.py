"""Background job: move old audit log entries into the archive table.

Like every job handler in app/jobs/, this receives a ScopedRepositories
instance already bound to the job's own organization (see
app/jobs/scoped_repositories.py and app/jobs/queue.py). It never imports
app.repositories.* directly and has no parameter through which it could
address a different organization.
"""

from datetime import datetime, timedelta, timezone

from app.jobs.handlers import register

JOB_TYPE = "audit_log_archival"
DEFAULT_OLDER_THAN_DAYS = 90


def _now():
    return datetime.now(timezone.utc).isoformat()


def _days_before(now_iso, days):
    now_dt = datetime.fromisoformat(now_iso)
    return (now_dt - timedelta(days=days)).isoformat()


def handle(scope, payload):
    older_than_days = payload.get("older_than_days", DEFAULT_OLDER_THAN_DAYS)
    now = payload.get("now") or _now()
    cutoff = _days_before(now, older_than_days)

    entries = scope.list_audit_log_older_than(cutoff)
    if entries:
        scope.archive_audit_log_entries(entries, now=now)
        scope.delete_audit_log_ids([entry.id for entry in entries])

    return {"archived_count": len(entries)}


register(JOB_TYPE, handle)
