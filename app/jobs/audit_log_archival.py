"""Background job: move old audit log entries into the archive table.

Like every job handler in app/jobs/, this reads organization_id from its
own payload (see app/jobs/queue.py) and threads it through to every
repository call it makes. Nothing outside this function enforces that it
does so correctly.
"""

from datetime import datetime, timedelta, timezone

from app.jobs.handlers import register
from app.repositories import audit_log

JOB_TYPE = "audit_log_archival"
DEFAULT_OLDER_THAN_DAYS = 90


def _now():
    return datetime.now(timezone.utc).isoformat()


def _days_before(now_iso, days):
    now_dt = datetime.fromisoformat(now_iso)
    return (now_dt - timedelta(days=days)).isoformat()


def handle(conn, payload):
    organization_id = payload["organization_id"]
    older_than_days = payload.get("older_than_days", DEFAULT_OLDER_THAN_DAYS)
    now = payload.get("now") or _now()
    cutoff = _days_before(now, older_than_days)

    entries = audit_log.list_older_than(conn, organization_id, cutoff)
    if entries:
        audit_log.archive_entries(conn, organization_id, entries, now=now)
        audit_log.delete_ids(conn, organization_id, [entry.id for entry in entries])

    return {"archived_count": len(entries)}


register(JOB_TYPE, handle)
