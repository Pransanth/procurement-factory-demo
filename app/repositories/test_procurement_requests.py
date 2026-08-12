import unittest

from app.db import init_db
from app.repositories import organizations, procurement_requests, suppliers, users


class TestProcurementRequestsRepository(unittest.TestCase):
    def setUp(self):
        self.conn = init_db(":memory:")
        self.org_a = organizations.create(self.conn, "Org A")
        self.org_b = organizations.create(self.conn, "Org B")
        self.user_a = users.create(self.conn, self.org_a.id, "alice@a.example", "Alice", "member")
        self.supplier_a = suppliers.create(self.conn, self.org_a.id, "Office Supplies Ltd")

    def _create_request(self, now=None):
        return procurement_requests.create(
            self.conn,
            self.org_a.id,
            self.user_a.id,
            self.supplier_a.id,
            "Laptops for new hires",
            250_000,
            now=now,
        )

    def test_create_defaults_to_draft(self):
        request = self._create_request()
        self.assertEqual(request.status, "draft")
        self.assertEqual(request.currency, "EUR")

    def test_get_by_id_wrong_org_returns_none(self):
        request = self._create_request()
        self.assertIsNone(procurement_requests.get_by_id(self.conn, self.org_b.id, request.id))

    def test_list_for_org_only_returns_own_requests(self):
        self._create_request()
        requests = procurement_requests.list_for_org(self.conn, self.org_a.id)
        self.assertEqual(len(requests), 1)
        self.assertEqual(procurement_requests.list_for_org(self.conn, self.org_b.id), [])

    def test_update_status(self):
        request = self._create_request()
        updated = procurement_requests.update_status(self.conn, self.org_a.id, request.id, "submitted")
        self.assertEqual(updated.status, "submitted")

    def test_list_pending_older_than_threshold(self):
        old_request = self._create_request(now="2026-01-01T00:00:00+00:00")
        procurement_requests.update_status(
            self.conn, self.org_a.id, old_request.id, "submitted", now="2026-01-01T00:00:00+00:00"
        )
        recent_request = self._create_request(now="2026-06-01T00:00:00+00:00")
        procurement_requests.update_status(
            self.conn, self.org_a.id, recent_request.id, "submitted", now="2026-06-01T00:00:00+00:00"
        )

        pending = procurement_requests.list_pending_older_than(
            self.conn, self.org_a.id, "2026-03-01T00:00:00+00:00"
        )
        self.assertEqual([r.id for r in pending], [old_request.id])


if __name__ == "__main__":
    unittest.main()
