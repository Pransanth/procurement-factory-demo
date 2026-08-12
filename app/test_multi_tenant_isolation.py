"""Cross-cutting multi-tenant isolation tests.

These are POSITIVE isolation tests: two organizations each get their own
data, and every repository is checked to never leak one org's rows into
the other's reads. The background job case here always uses the CORRECT
organization_id for the org it's meant to touch — it demonstrates that a
correctly-written job does not cross tenant boundaries.

This file deliberately does NOT construct a job with a WRONG
organization_id and assert that it gets rejected or blocked. That
adversarial regression test is reserved for after finding P1-DEMO-1 has
been analyzed — it is not part of this baseline test suite.
"""

import unittest

from app.db import init_db
from app.jobs import approval_reminder, queue  # noqa: F401 (import registers the handler)
from app.repositories import (
    approvals,
    audit_log,
    organizations,
    procurement_requests,
    suppliers,
    users,
)


class TestMultiTenantIsolation(unittest.TestCase):
    def setUp(self):
        self.conn = init_db(":memory:")
        self.org_a = organizations.create(self.conn, "Org A")
        self.org_b = organizations.create(self.conn, "Org B")

        self.user_a = users.create(self.conn, self.org_a.id, "alice@a.example", "Alice", "member")
        self.approver_a = users.create(self.conn, self.org_a.id, "carol@a.example", "Carol", "approver")
        self.supplier_a = suppliers.create(self.conn, self.org_a.id, "A Supplies")
        self.request_a = procurement_requests.create(
            self.conn, self.org_a.id, self.user_a.id, self.supplier_a.id, "A's laptops", 100_000,
            now="2026-01-01T00:00:00+00:00",
        )
        procurement_requests.update_status(
            self.conn, self.org_a.id, self.request_a.id, "submitted", now="2026-01-01T00:00:00+00:00"
        )
        audit_log.record(self.conn, self.org_a.id, action="seed", entity_type="t")

        self.user_b = users.create(self.conn, self.org_b.id, "bob@b.example", "Bob", "member")
        self.approver_b = users.create(self.conn, self.org_b.id, "dave@b.example", "Dave", "approver")
        self.supplier_b = suppliers.create(self.conn, self.org_b.id, "B Supplies")
        self.request_b = procurement_requests.create(
            self.conn, self.org_b.id, self.user_b.id, self.supplier_b.id, "B's laptops", 200_000,
            now="2026-01-01T00:00:00+00:00",
        )
        procurement_requests.update_status(
            self.conn, self.org_b.id, self.request_b.id, "submitted", now="2026-01-01T00:00:00+00:00"
        )
        audit_log.record(self.conn, self.org_b.id, action="seed", entity_type="t")

    def test_users_are_isolated(self):
        self.assertEqual([u.id for u in users.list_for_org(self.conn, self.org_a.id)], [self.user_a.id, self.approver_a.id])
        self.assertIsNone(users.get_by_id(self.conn, self.org_a.id, self.user_b.id))
        self.assertIsNone(users.get_by_id(self.conn, self.org_b.id, self.user_a.id))

    def test_suppliers_are_isolated(self):
        self.assertEqual([s.id for s in suppliers.list_for_org(self.conn, self.org_a.id)], [self.supplier_a.id])
        self.assertIsNone(suppliers.get_by_id(self.conn, self.org_a.id, self.supplier_b.id))

    def test_procurement_requests_are_isolated(self):
        self.assertEqual(
            [r.id for r in procurement_requests.list_for_org(self.conn, self.org_a.id)], [self.request_a.id]
        )
        self.assertIsNone(procurement_requests.get_by_id(self.conn, self.org_a.id, self.request_b.id))

    def test_approvals_cannot_cross_organizations(self):
        with self.assertRaises(ValueError):
            approvals.record_decision(
                self.conn, self.org_a.id, self.request_b.id, self.approver_a.id, "approved"
            )
        with self.assertRaises(ValueError):
            approvals.record_decision(
                self.conn, self.org_a.id, self.request_a.id, self.approver_b.id, "approved"
            )

    def test_audit_log_is_isolated(self):
        self.assertEqual(len(audit_log.list_for_org(self.conn, self.org_a.id)), 1)
        self.assertEqual(len(audit_log.list_for_org(self.conn, self.org_b.id)), 1)

    def test_job_run_with_correct_org_id_only_touches_its_own_org(self):
        """A background job given org A's own correct organization_id must
        never affect org B's data, even though run_pending() processes a
        single global queue spanning both organizations.
        """
        job_id = queue.enqueue(
            self.conn,
            "approval_reminder",
            self.org_a.id,
            payload={"older_than_hours": 1, "now": "2026-01-02T00:00:00+00:00"},
        )
        results = queue.run_pending(self.conn, now="2026-01-02T00:00:00+00:00")

        self.assertEqual(results, [{"job_id": job_id, "status": "succeeded"}])

        org_a_actions = [e.action for e in audit_log.list_for_org(self.conn, self.org_a.id)]
        self.assertIn("approval_reminder.sent", org_a_actions)

        org_b_actions = [e.action for e in audit_log.list_for_org(self.conn, self.org_b.id)]
        self.assertNotIn("approval_reminder.sent", org_b_actions)
        self.assertEqual(len(org_b_actions), 1)  # only the seed entry from setUp


if __name__ == "__main__":
    unittest.main()
