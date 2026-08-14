"""Regression tests for finding P1-DEMO-5.

app/services/user_admin_service.py:change_user_role() decided who may
administer roles by exclusion -- it rejected only the role 'member'. The
middle role 'approver', which exists to decide procurement requests and
carries no administrative authority, therefore passed the check and could
assign any role, including 'admin', including to itself.

These tests are adversarial about the actor's role rather than about the
organization boundary (which was never broken here). They were written
against the unfixed code and proven red there (see
factory/build-orders/P1-DEMO-5.md, "Red Regression Evidence").
"""

import unittest

from app.db import init_db
from app.repositories import audit_log, organizations, users
from app.services import user_admin_service


class TestChangeUserRoleEscalation(unittest.TestCase):
    def setUp(self):
        self.conn = init_db(":memory:")
        self.org = organizations.create(self.conn, "Acme Corp")

        self.approver = users.create(
            self.conn, self.org.id, "carol@acme.example", "Carol", "approver"
        )
        self.member = users.create(
            self.conn, self.org.id, "alice@acme.example", "Alice", "member"
        )
        self.admin = users.create(self.conn, self.org.id, "root@acme.example", "Root", "admin")

    # The message is pinned, not just the exception type: every other
    # ValueError this function can raise (unassignable role, actor or target
    # not in the organization) would otherwise satisfy assertRaises and let
    # the authorization check itself disappear unnoticed.
    NOT_AUTHORIZED = "not authorized to administer user roles"

    def test_approver_cannot_promote_themselves_to_admin(self):
        with self.assertRaisesRegex(ValueError, self.NOT_AUTHORIZED):
            user_admin_service.change_user_role(
                self.conn, self.org.id, self.approver.id, self.approver.id, "admin"
            )
        self.assertEqual(
            users.get_by_id(self.conn, self.org.id, self.approver.id).role, "approver"
        )

    def test_approver_cannot_promote_a_colleague(self):
        with self.assertRaisesRegex(ValueError, self.NOT_AUTHORIZED):
            user_admin_service.change_user_role(
                self.conn, self.org.id, self.approver.id, self.member.id, "admin"
            )
        self.assertEqual(users.get_by_id(self.conn, self.org.id, self.member.id).role, "member")

    def test_rejected_escalation_writes_no_audit_log_entry(self):
        with self.assertRaisesRegex(ValueError, self.NOT_AUTHORIZED):
            user_admin_service.change_user_role(
                self.conn, self.org.id, self.approver.id, self.approver.id, "admin"
            )
        self.assertEqual(audit_log.list_for_org(self.conn, self.org.id), [])

    def test_admin_can_still_promote_a_member(self):
        updated = user_admin_service.change_user_role(
            self.conn, self.org.id, self.admin.id, self.member.id, "approver"
        )
        self.assertEqual(updated.role, "approver")
        self.assertEqual(
            users.get_by_id(self.conn, self.org.id, self.member.id).role, "approver"
        )

    def test_admin_may_still_demote_themselves(self):
        # Deliberately permitted, and pinned here so the decision cannot be
        # reversed silently: the fix adds no self-change ban, because with an
        # admin-only allowlist a self-change can only reduce privilege, and
        # forbidding it would remove the only way an admin can step down.
        # (Contrast P1-DEMO-3, where self-approval is barred regardless of
        # role, because deciding one's own request is an integrity problem.)
        updated = user_admin_service.change_user_role(
            self.conn, self.org.id, self.admin.id, self.admin.id, "member"
        )
        self.assertEqual(updated.role, "member")
        self.assertEqual(users.get_by_id(self.conn, self.org.id, self.admin.id).role, "member")


if __name__ == "__main__":
    unittest.main()
