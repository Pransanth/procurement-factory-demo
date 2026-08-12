import unittest

from app.db import init_db
from app.repositories import audit_log, organizations, procurement_requests, suppliers, users
from app.services import procurement_service


class TestProcurementService(unittest.TestCase):
    def setUp(self):
        self.conn = init_db(":memory:")
        self.org = organizations.create(self.conn, "Acme Corp")
        self.requester = users.create(self.conn, self.org.id, "alice@acme.example", "Alice", "member")
        self.approver = users.create(self.conn, self.org.id, "carol@acme.example", "Carol", "approver")
        self.supplier = suppliers.create(self.conn, self.org.id, "Office Supplies Ltd")

    def test_happy_path_create_submit_approve(self):
        request = procurement_service.create_request(
            self.conn, self.org.id, self.requester.id, self.supplier.id, "Laptops for new hires", 250_000
        )
        self.assertEqual(request.status, "draft")

        submitted = procurement_service.submit_request(self.conn, self.org.id, request.id, self.requester.id)
        self.assertEqual(submitted.status, "submitted")

        approval = procurement_service.decide_request(
            self.conn, self.org.id, request.id, self.approver.id, "approved", comment="Approved for Q1 budget"
        )
        self.assertEqual(approval.decision, "approved")

        final_request = procurement_requests.get_by_id(self.conn, self.org.id, request.id)
        self.assertEqual(final_request.status, "approved")

        actions = [entry.action for entry in audit_log.list_for_org(self.conn, self.org.id)]
        self.assertEqual(
            actions,
            [
                "procurement_request.created",
                "procurement_request.submitted",
                "procurement_request.approved",
            ],
        )

    def test_reject_path(self):
        request = procurement_service.create_request(
            self.conn, self.org.id, self.requester.id, self.supplier.id, "Gold-plated keyboards", 999_999
        )
        procurement_service.submit_request(self.conn, self.org.id, request.id, self.requester.id)
        procurement_service.decide_request(self.conn, self.org.id, request.id, self.approver.id, "rejected")

        final_request = procurement_requests.get_by_id(self.conn, self.org.id, request.id)
        self.assertEqual(final_request.status, "rejected")

    def test_cannot_submit_twice(self):
        request = procurement_service.create_request(
            self.conn, self.org.id, self.requester.id, self.supplier.id, "Laptops", 250_000
        )
        procurement_service.submit_request(self.conn, self.org.id, request.id, self.requester.id)
        with self.assertRaises(ValueError):
            procurement_service.submit_request(self.conn, self.org.id, request.id, self.requester.id)

    def test_cannot_decide_on_draft_request(self):
        request = procurement_service.create_request(
            self.conn, self.org.id, self.requester.id, self.supplier.id, "Laptops", 250_000
        )
        with self.assertRaises(ValueError):
            procurement_service.decide_request(self.conn, self.org.id, request.id, self.approver.id, "approved")


if __name__ == "__main__":
    unittest.main()
