import unittest

from app.db import init_db
from app.jobs import audit_log_archival, queue
from app.jobs.scoped_repositories import ScopedRepositories
from app.repositories import audit_log, organizations


class TestAuditLogArchivalJob(unittest.TestCase):
    def setUp(self):
        self.conn = init_db(":memory:")
        self.org = organizations.create(self.conn, "Acme Corp")

    def test_archives_only_old_entries(self):
        old_entry = audit_log.record(
            self.conn, self.org.id, action="old", entity_type="t", now="2026-01-01T00:00:00+00:00"
        )
        recent_entry = audit_log.record(
            self.conn, self.org.id, action="recent", entity_type="t", now="2026-06-01T00:00:00+00:00"
        )

        scope = ScopedRepositories(self.conn, self.org.id)
        result = audit_log_archival.handle(
            scope,
            {"older_than_days": 90, "now": "2026-06-02T00:00:00+00:00"},
        )

        self.assertEqual(result["archived_count"], 1)

        remaining_actions = [e.action for e in audit_log.list_for_org(self.conn, self.org.id)]
        self.assertEqual(remaining_actions, ["recent"])

        archived_row = self.conn.execute(
            "SELECT * FROM audit_log_archive WHERE id = ?", (old_entry.id,)
        ).fetchone()
        self.assertIsNotNone(archived_row)
        self.assertEqual(archived_row["action"], "old")
        self.assertIsNone(
            self.conn.execute("SELECT * FROM audit_log_archive WHERE id = ?", (recent_entry.id,)).fetchone()
        )

    def test_nothing_to_archive_is_a_no_op(self):
        scope = ScopedRepositories(self.conn, self.org.id)
        result = audit_log_archival.handle(scope, {})
        self.assertEqual(result, {"archived_count": 0})

    def test_runs_end_to_end_through_the_queue(self):
        old_entry = audit_log.record(
            self.conn, self.org.id, action="old", entity_type="t", now="2026-01-01T00:00:00+00:00"
        )

        job_id = queue.enqueue(
            self.conn,
            "audit_log_archival",
            self.org.id,
            payload={"older_than_days": 90, "now": "2026-06-02T00:00:00+00:00"},
        )
        results = queue.run_pending(self.conn, now="2026-06-02T00:00:00+00:00")

        self.assertEqual(results, [{"job_id": job_id, "status": "succeeded"}])
        self.assertIsNone(audit_log.get_by_id(self.conn, self.org.id, old_entry.id))


if __name__ == "__main__":
    unittest.main()
