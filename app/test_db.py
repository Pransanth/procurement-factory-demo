import sqlite3
import unittest

from app.db import init_db


class TestInitDb(unittest.TestCase):
    def setUp(self):
        self.conn = init_db(":memory:")

    def test_creates_all_tables(self):
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
        table_names = {row["name"] for row in rows}
        expected = {
            "organizations",
            "users",
            "suppliers",
            "procurement_requests",
            "approvals",
            "audit_log",
            "audit_log_archive",
            "jobs",
        }
        self.assertTrue(expected.issubset(table_names))

    def test_foreign_keys_are_enforced(self):
        pragma_value = self.conn.execute("PRAGMA foreign_keys").fetchone()[0]
        self.assertEqual(pragma_value, 1)

        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO users (organization_id, email, display_name, role, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (999, "nobody@example.com", "Nobody", "member", "2026-01-01T00:00:00+00:00"),
            )

    def test_role_check_constraint(self):
        self.conn.execute(
            "INSERT INTO organizations (name, created_at) VALUES (?, ?)",
            ("Acme", "2026-01-01T00:00:00+00:00"),
        )
        org_id = self.conn.execute("SELECT id FROM organizations").fetchone()["id"]

        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO users (organization_id, email, display_name, role, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (org_id, "x@example.com", "X", "not-a-real-role", "2026-01-01T00:00:00+00:00"),
            )


if __name__ == "__main__":
    unittest.main()
