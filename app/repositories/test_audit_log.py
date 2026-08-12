import unittest

from app.db import init_db
from app.repositories import audit_log, organizations


class TestAuditLogRepository(unittest.TestCase):
    def setUp(self):
        self.conn = init_db(":memory:")
        self.org_a = organizations.create(self.conn, "Org A")
        self.org_b = organizations.create(self.conn, "Org B")

    def test_record_and_get_by_id(self):
        entry = audit_log.record(
            self.conn,
            self.org_a.id,
            action="procurement_request.created",
            entity_type="procurement_request",
            entity_id=42,
            details={"amount_cents": 1000},
        )
        fetched = audit_log.get_by_id(self.conn, self.org_a.id, entry.id)
        self.assertEqual(fetched.action, "procurement_request.created")
        self.assertIn('"amount_cents": 1000', fetched.details)

    def test_actor_user_id_optional_for_system_actions(self):
        entry = audit_log.record(
            self.conn, self.org_a.id, action="approval_reminder.sent", entity_type="procurement_request"
        )
        self.assertIsNone(entry.actor_user_id)

    def test_list_for_org_scoping(self):
        audit_log.record(self.conn, self.org_a.id, action="a", entity_type="t")
        audit_log.record(self.conn, self.org_b.id, action="b", entity_type="t")

        org_a_entries = audit_log.list_for_org(self.conn, self.org_a.id)
        self.assertEqual(len(org_a_entries), 1)
        self.assertEqual(org_a_entries[0].action, "a")

    def test_list_older_than_threshold(self):
        audit_log.record(self.conn, self.org_a.id, action="old", entity_type="t", now="2026-01-01T00:00:00+00:00")
        audit_log.record(self.conn, self.org_a.id, action="new", entity_type="t", now="2026-06-01T00:00:00+00:00")

        old_entries = audit_log.list_older_than(self.conn, self.org_a.id, "2026-03-01T00:00:00+00:00")
        self.assertEqual([e.action for e in old_entries], ["old"])

    def test_archive_then_delete_round_trip(self):
        entry = audit_log.record(self.conn, self.org_a.id, action="old", entity_type="t")
        audit_log.archive_entries(self.conn, self.org_a.id, [entry])
        audit_log.delete_ids(self.conn, self.org_a.id, [entry.id])

        self.assertIsNone(audit_log.get_by_id(self.conn, self.org_a.id, entry.id))
        archived_row = self.conn.execute(
            "SELECT * FROM audit_log_archive WHERE organization_id = ? AND id = ?",
            (self.org_a.id, entry.id),
        ).fetchone()
        self.assertIsNotNone(archived_row)
        self.assertEqual(archived_row["action"], "old")


if __name__ == "__main__":
    unittest.main()
