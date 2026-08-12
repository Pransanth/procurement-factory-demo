import unittest

from app.db import init_db
from app.repositories import organizations


class TestOrganizationsRepository(unittest.TestCase):
    def setUp(self):
        self.conn = init_db(":memory:")

    def test_create_and_get_by_id(self):
        org = organizations.create(self.conn, "Acme Corp")
        fetched = organizations.get_by_id(self.conn, org.id)
        self.assertEqual(fetched, org)
        self.assertEqual(fetched.name, "Acme Corp")

    def test_get_by_id_missing_returns_none(self):
        self.assertIsNone(organizations.get_by_id(self.conn, 999))

    def test_get_by_name(self):
        organizations.create(self.conn, "Acme Corp")
        fetched = organizations.get_by_name(self.conn, "Acme Corp")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "Acme Corp")
        self.assertIsNone(organizations.get_by_name(self.conn, "Nonexistent"))

    def test_name_must_be_unique(self):
        organizations.create(self.conn, "Acme Corp")
        with self.assertRaises(Exception):
            organizations.create(self.conn, "Acme Corp")

    def test_list_all(self):
        organizations.create(self.conn, "Acme Corp")
        organizations.create(self.conn, "Globex Inc")
        names = {org.name for org in organizations.list_all(self.conn)}
        self.assertEqual(names, {"Acme Corp", "Globex Inc"})


if __name__ == "__main__":
    unittest.main()
