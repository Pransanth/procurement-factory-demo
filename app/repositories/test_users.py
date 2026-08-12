import unittest

from app.db import init_db
from app.repositories import organizations, users


class TestUsersRepository(unittest.TestCase):
    def setUp(self):
        self.conn = init_db(":memory:")
        self.org_a = organizations.create(self.conn, "Org A")
        self.org_b = organizations.create(self.conn, "Org B")

    def test_create_and_get_by_id(self):
        user = users.create(self.conn, self.org_a.id, "alice@a.example", "Alice", "member")
        fetched = users.get_by_id(self.conn, self.org_a.id, user.id)
        self.assertEqual(fetched, user)

    def test_get_by_id_wrong_org_returns_none(self):
        user = users.create(self.conn, self.org_a.id, "alice@a.example", "Alice", "member")
        self.assertIsNone(users.get_by_id(self.conn, self.org_b.id, user.id))

    def test_list_for_org_only_returns_own_users(self):
        users.create(self.conn, self.org_a.id, "alice@a.example", "Alice", "member")
        users.create(self.conn, self.org_b.id, "bob@b.example", "Bob", "member")

        org_a_users = users.list_for_org(self.conn, self.org_a.id)
        self.assertEqual(len(org_a_users), 1)
        self.assertEqual(org_a_users[0].email, "alice@a.example")

    def test_email_unique_per_org_not_globally(self):
        users.create(self.conn, self.org_a.id, "shared@example.com", "Alice", "member")
        # Same email in a different org is fine.
        users.create(self.conn, self.org_b.id, "shared@example.com", "Bob", "member")

        with self.assertRaises(Exception):
            users.create(self.conn, self.org_a.id, "shared@example.com", "Someone Else", "member")

    def test_invalid_role_rejected(self):
        with self.assertRaises(Exception):
            users.create(self.conn, self.org_a.id, "x@a.example", "X", "superuser")


if __name__ == "__main__":
    unittest.main()
