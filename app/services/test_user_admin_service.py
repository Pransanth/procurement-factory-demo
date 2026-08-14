"""Baseline tests for app/services/user_admin_service.py.

These cover the intended administrative path (an admin changes a colleague's
role), the organization boundary (an actor or target from another
organization is not found), and the input validation for the role value
itself.

This file deliberately does NOT assert which non-admin roles are allowed to
administer roles, nor what happens when a user changes their own role. Those
adversarial privilege-escalation regression tests are reserved for after
finding P1-DEMO-5 has been analyzed — they are not part of this baseline
test suite.
"""

import unittest

from app.db import init_db
from app.repositories import audit_log, organizations, users
from app.services import user_admin_service


class TestChangeUserRole(unittest.TestCase):
    def setUp(self):
        self.conn = init_db(":memory:")
        self.org = organizations.create(self.conn, "Acme Corp")
        self.other_org = organizations.create(self.conn, "Globex")

        self.admin = users.create(self.conn, self.org.id, "root@acme.example", "Root", "admin")
        self.member = users.create(self.conn, self.org.id, "alice@acme.example", "Alice", "member")
        self.other_admin = users.create(
            self.conn, self.other_org.id, "root@globex.example", "Rex", "admin"
        )

    def test_admin_can_promote_a_member(self):
        updated = user_admin_service.change_user_role(
            self.conn, self.org.id, self.admin.id, self.member.id, "approver"
        )
        self.assertEqual(updated.role, "approver")
        self.assertEqual(
            users.get_by_id(self.conn, self.org.id, self.member.id).role, "approver"
        )

    def test_role_change_is_recorded_in_the_audit_log(self):
        user_admin_service.change_user_role(
            self.conn, self.org.id, self.admin.id, self.member.id, "approver"
        )
        entries = audit_log.list_for_org(self.conn, self.org.id)
        self.assertEqual([entry.action for entry in entries], ["user.role_changed"])
        self.assertEqual(entries[0].actor_user_id, self.admin.id)
        self.assertEqual(entries[0].entity_id, self.member.id)

    def test_plain_member_cannot_change_roles(self):
        with self.assertRaises(ValueError):
            user_admin_service.change_user_role(
                self.conn, self.org.id, self.member.id, self.admin.id, "member"
            )
        self.assertEqual(users.get_by_id(self.conn, self.org.id, self.admin.id).role, "admin")

    def test_unknown_role_is_rejected(self):
        with self.assertRaises(ValueError):
            user_admin_service.change_user_role(
                self.conn, self.org.id, self.admin.id, self.member.id, "superadmin"
            )
        self.assertEqual(users.get_by_id(self.conn, self.org.id, self.member.id).role, "member")

    def test_actor_from_another_organization_is_not_found(self):
        with self.assertRaises(ValueError):
            user_admin_service.change_user_role(
                self.conn, self.org.id, self.other_admin.id, self.member.id, "approver"
            )
        self.assertEqual(users.get_by_id(self.conn, self.org.id, self.member.id).role, "member")

    def test_target_from_another_organization_is_not_found(self):
        with self.assertRaises(ValueError):
            user_admin_service.change_user_role(
                self.conn, self.org.id, self.admin.id, self.other_admin.id, "member"
            )
        self.assertEqual(
            users.get_by_id(self.conn, self.other_org.id, self.other_admin.id).role, "admin"
        )


if __name__ == "__main__":
    unittest.main()
