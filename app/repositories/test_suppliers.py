import unittest

from app.db import init_db
from app.repositories import organizations, suppliers


class TestSuppliersRepository(unittest.TestCase):
    def setUp(self):
        self.conn = init_db(":memory:")
        self.org_a = organizations.create(self.conn, "Org A")
        self.org_b = organizations.create(self.conn, "Org B")

    def test_create_and_get_by_id(self):
        supplier = suppliers.create(self.conn, self.org_a.id, "Office Supplies Ltd")
        fetched = suppliers.get_by_id(self.conn, self.org_a.id, supplier.id)
        self.assertEqual(fetched, supplier)

    def test_get_by_id_wrong_org_returns_none(self):
        supplier = suppliers.create(self.conn, self.org_a.id, "Office Supplies Ltd")
        self.assertIsNone(suppliers.get_by_id(self.conn, self.org_b.id, supplier.id))

    def test_list_for_org_only_returns_own_suppliers(self):
        suppliers.create(self.conn, self.org_a.id, "Office Supplies Ltd")
        suppliers.create(self.conn, self.org_b.id, "IT Hardware Co")

        org_a_suppliers = suppliers.list_for_org(self.conn, self.org_a.id)
        self.assertEqual(len(org_a_suppliers), 1)
        self.assertEqual(org_a_suppliers[0].name, "Office Supplies Ltd")

    def test_name_unique_per_org_not_globally(self):
        suppliers.create(self.conn, self.org_a.id, "Shared Name Inc")
        # Same name in a different org is fine.
        suppliers.create(self.conn, self.org_b.id, "Shared Name Inc")

        with self.assertRaises(Exception):
            suppliers.create(self.conn, self.org_a.id, "Shared Name Inc")


if __name__ == "__main__":
    unittest.main()
