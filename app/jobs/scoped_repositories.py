"""The primary runtime security boundary for background jobs.

A ScopedRepositories instance is permanently bound to exactly one
organization_id for its entire lifetime. It is constructed exactly once
per job execution, centrally, by app/jobs/queue.py:run_pending() — from
the job's own `organization_id` column (the value the queue itself
recorded when the job was enqueued), never from the job's payload. A
handler receives only this bound object; none of its methods accept an
organization_id argument, so there is no parameter through which a
handler could name a different organization.

This is a thin wrapper (bound method calls) around the existing
repository functions in app/repositories/*.py — it does not duplicate any
query logic. The unbound repository functions are unchanged and continue
to be used directly by the interactive path
(app/services/procurement_service.py), which is out of scope here.

Only the methods actually needed by a job handler today are exposed
(app/jobs/approval_reminder.py, app/jobs/audit_log_archival.py, and the
regression test in app/jobs/test_org_scope_regression.py that proves this
boundary holds). This is deliberately not a full facade over every
repository — new methods should be added only when a real handler needs
them.
"""

from app.repositories import audit_log, procurement_requests


class ScopedRepositories:
    """Tenant-bound facade over the org-scoped repositories used by jobs."""

    def __init__(self, conn, organization_id):
        self._conn = conn
        self.organization_id = organization_id

    def list_pending_procurement_requests_older_than(self, cutoff):
        return procurement_requests.list_pending_older_than(self._conn, self.organization_id, cutoff)

    def update_procurement_request_status(self, request_id, status, now=None):
        return procurement_requests.update_status(
            self._conn, self.organization_id, request_id, status, now=now
        )

    def record_audit_log(self, action, entity_type, entity_id=None, actor_user_id=None, details=None, now=None):
        return audit_log.record(
            self._conn,
            self.organization_id,
            action,
            entity_type,
            entity_id=entity_id,
            actor_user_id=actor_user_id,
            details=details,
            now=now,
        )

    def list_audit_log_older_than(self, cutoff):
        return audit_log.list_older_than(self._conn, self.organization_id, cutoff)

    def archive_audit_log_entries(self, entries, now=None):
        return audit_log.archive_entries(self._conn, self.organization_id, entries, now=now)

    def delete_audit_log_ids(self, ids):
        return audit_log.delete_ids(self._conn, self.organization_id, ids)
