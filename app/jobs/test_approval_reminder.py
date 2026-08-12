import unittest

from app.db import init_db
from app.jobs import approval_reminder, queue
from app.repositories import audit_log, organizations, procurement_requests, suppliers, users


class TestApprovalReminderJob(unittest.TestCase):
    def setUp(self):
        self.conn = init_db(":memory:")
        self.org = organizations.create(self.conn, "Acme Corp")
        self.requester = users.create(self.conn, self.org.id, "alice@acme.example", "Alice", "member")
        self.supplier = suppliers.create(self.conn, self.org.id, "Office Supplies Ltd")

    def _submitted_request(self, updated_at):
        request = procurement_requests.create(
            self.conn, self.org.id, self.requester.id, self.supplier.id, "Laptops", 250_000,
            now=updated_at,
        )
        return procurement_requests.update_status(self.conn, self.org.id, request.id, "submitted", now=updated_at)

    def test_reminds_only_old_pending_requests(self):
        old_request = self._submitted_request("2026-01-01T00:00:00+00:00")
        recent_request = self._submitted_request("2026-06-01T00:00:00+00:00")

        result = approval_reminder.handle(
            self.conn,
            {"organization_id": self.org.id, "older_than_hours": 24, "now": "2026-06-02T00:00:00+00:00"},
        )

        self.assertEqual(result["reminded_count"], 1)
        self.assertEqual(result["request_ids"], [old_request.id])

        actions = [entry.action for entry in audit_log.list_for_org(self.conn, self.org.id)]
        self.assertEqual(actions, ["approval_reminder.sent"])

    def test_no_pending_requests_means_no_reminders(self):
        result = approval_reminder.handle(self.conn, {"organization_id": self.org.id})
        self.assertEqual(result, {"reminded_count": 0, "request_ids": []})

    def test_runs_end_to_end_through_the_queue(self):
        old_request = self._submitted_request("2026-01-01T00:00:00+00:00")

        job_id = queue.enqueue(
            self.conn,
            "approval_reminder",
            self.org.id,
            payload={"older_than_hours": 24, "now": "2026-06-02T00:00:00+00:00"},
        )
        results = queue.run_pending(self.conn, now="2026-06-02T00:00:00+00:00")

        self.assertEqual(results, [{"job_id": job_id, "status": "succeeded"}])
        job = queue.get_by_id(self.conn, job_id)
        self.assertIn(str(old_request.id), job.result)


if __name__ == "__main__":
    unittest.main()
