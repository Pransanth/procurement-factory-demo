"""Regression test for P1-DEMO-2.

See factory/findings/P1-DEMO-2.md for the full analysis. Root cause:
app/repositories/procurement_requests.py:create() inserts a procurement
request with a caller-supplied supplier_id without checking that the
referenced supplier actually belongs to the request's own organization_id.

This test must be red against the unmodified repository function (it
raises no error and silently inserts a cross-organization row) and green
once create() validates the supplier via suppliers.get_by_id(conn,
organization_id, supplier_id) before inserting.
"""
import unittest

from app.db import init_db
from app.repositories import organizations, procurement_requests, suppliers, users


class TestSupplierOrgScopeRegressionP1Demo2(unittest.TestCase):
    def test_create_rejects_supplier_from_another_organization(self):
        conn = init_db(":memory:")
        org_a = organizations.create(conn, "Org A")
        org_b = organizations.create(conn, "Org B")

        user_a = users.create(conn, org_a.id, "alice@a.example", "Alice", "member")
        supplier_b = suppliers.create(conn, org_b.id, "B Supplies (secret vendor)")

        with self.assertRaises(ValueError):
            procurement_requests.create(
                conn, org_a.id, user_a.id, supplier_b.id, "sneaky", 50_000
            )

        # No row must have been inserted for Org A as a side effect of the
        # rejected call.
        self.assertEqual(procurement_requests.list_for_org(conn, org_a.id), [])


if __name__ == "__main__":
    unittest.main()
