import unittest

from app.db import init_db
from app.repositories import approvals, organizations, procurement_requests, suppliers, users


class TestApprovalsRepository(unittest.TestCase):
    def setUp(self):
        self.conn = init_db(":memory:")
        self.org_a = organizations.create(self.conn, "Org A")
        self.org_b = organizations.create(self.conn, "Org B")
        self.requester = users.create(self.conn, self.org_a.id, "alice@a.example", "Alice", "member")
        self.approver = users.create(self.conn, self.org_a.id, "carol@a.example", "Carol", "approver")
        self.supplier = suppliers.create(self.conn, self.org_a.id, "Office Supplies Ltd")
        self.request = procurement_requests.create(
            self.conn, self.org_a.id, self.requester.id, self.supplier.id, "Laptops", 250_000
        )
        procurement_requests.update_status(self.conn, self.org_a.id, self.request.id, "submitted")

    def test_record_decision_approves_request(self):
        approval = approvals.record_decision(
            self.conn, self.org_a.id, self.request.id, self.approver.id, "approved", comment="Looks good"
        )
        self.assertEqual(approval.decision, "approved")

        updated_request = procurement_requests.get_by_id(self.conn, self.org_a.id, self.request.id)
        self.assertEqual(updated_request.status, "approved")

    def test_record_decision_rejects_request(self):
        approvals.record_decision(self.conn, self.org_a.id, self.request.id, self.approver.id, "rejected")
        updated_request = procurement_requests.get_by_id(self.conn, self.org_a.id, self.request.id)
        self.assertEqual(updated_request.status, "rejected")

    def test_unknown_decision_value_rejected(self):
        with self.assertRaises(Exception):
            approvals.record_decision(self.conn, self.org_a.id, self.request.id, self.approver.id, "maybe")

    def test_request_from_other_org_raises(self):
        with self.assertRaises(ValueError):
            approvals.record_decision(self.conn, self.org_b.id, self.request.id, self.approver.id, "approved")

    def test_approver_from_other_org_raises(self):
        outsider = users.create(self.conn, self.org_b.id, "eve@b.example", "Eve", "approver")
        with self.assertRaises(ValueError):
            approvals.record_decision(self.conn, self.org_a.id, self.request.id, outsider.id, "approved")


if __name__ == "__main__":
    unittest.main()
