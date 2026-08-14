"""Regression tests for P1-DEMO-3.

See factory/findings/P1-DEMO-3.md for the full analysis. Root cause:
app/repositories/approvals.py:record_decision() validates that the request
and the approver belong to the given organization_id, but never checks the
approver's role (member/approver/admin) and never rejects self-approval
(the requester deciding on their own request).

Both tests must be red against the unmodified repository function (no
error is raised, a successful Approval with decision == "approved" is
returned) and green once record_decision() validates the approver's role
and rejects self-approval before inserting.
"""
import unittest

from app.db import init_db
from app.repositories import approvals, organizations, procurement_requests, suppliers, users


class TestApprovalRoleScopeRegressionP1Demo3(unittest.TestCase):
    def setUp(self):
        self.conn = init_db(":memory:")
        self.org_a = organizations.create(self.conn, "Org A")
        self.supplier = suppliers.create(self.conn, self.org_a.id, "A Supplies")

    def test_member_role_cannot_approve_a_request(self):
        member = users.create(self.conn, self.org_a.id, "mallory@a.example", "Mallory", "member")
        requester = users.create(self.conn, self.org_a.id, "bob@a.example", "Bob", "member")
        request = procurement_requests.create(
            self.conn, self.org_a.id, requester.id, self.supplier.id, "big purchase", 99_999_900
        )
        procurement_requests.update_status(self.conn, self.org_a.id, request.id, "submitted")

        with self.assertRaises(ValueError):
            approvals.record_decision(self.conn, self.org_a.id, request.id, member.id, "approved")

    def test_requester_cannot_approve_their_own_request(self):
        approver = users.create(self.conn, self.org_a.id, "carol@a.example", "Carol", "approver")
        request = procurement_requests.create(
            self.conn, self.org_a.id, approver.id, self.supplier.id, "self-serve purchase", 500_00
        )
        procurement_requests.update_status(self.conn, self.org_a.id, request.id, "submitted")

        with self.assertRaises(ValueError):
            approvals.record_decision(self.conn, self.org_a.id, request.id, approver.id, "approved")


if __name__ == "__main__":
    unittest.main()
