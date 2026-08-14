"""Baseline tests for app/services/reporting_service.py.

These tests are single-organization: one tenant's data is set up and the
report is checked against it. They establish that the report computes the
right numbers and picks the right line items for a normal, single-tenant
scenario.

This file deliberately does NOT set up a second organization and assert that
its data stays out of the report. That adversarial cross-organization
regression test is reserved for after finding P1-DEMO-4 has been analyzed —
it is not part of this baseline test suite.
"""

import unittest

from app.db import init_db
from app.repositories import organizations, procurement_requests, suppliers, users
from app.services import reporting_service

MARCH = "2026-03-05T09:00:00+00:00"
APRIL = "2026-04-02T09:00:00+00:00"


class TestMonthlySpendReport(unittest.TestCase):
    def setUp(self):
        self.conn = init_db(":memory:")
        self.org = organizations.create(self.conn, "Acme Corp")
        self.requester = users.create(
            self.conn, self.org.id, "alice@acme.example", "Alice", "member"
        )
        self.supplier = suppliers.create(self.conn, self.org.id, "Office Supplies Ltd")

    def _approved_request(self, description, amount_cents, now):
        request = procurement_requests.create(
            self.conn,
            self.org.id,
            self.requester.id,
            self.supplier.id,
            description,
            amount_cents,
            now=now,
        )
        procurement_requests.update_status(
            self.conn, self.org.id, request.id, "approved", now=now
        )
        return request

    def test_empty_month_reports_zero(self):
        report = reporting_service.monthly_spend_report(self.conn, self.org.id, "2026-03")
        self.assertEqual(report["organization_id"], self.org.id)
        self.assertEqual(report["month"], "2026-03")
        self.assertEqual(report["approved_request_count"], 0)
        self.assertEqual(report["approved_total_cents"], 0)
        self.assertEqual(report["top_line_items"], [])

    def test_totals_cover_only_the_requested_month(self):
        self._approved_request("Laptops", 250_000, MARCH)
        self._approved_request("Monitors", 90_000, MARCH)
        self._approved_request("Desks", 400_000, APRIL)

        report = reporting_service.monthly_spend_report(self.conn, self.org.id, "2026-03")
        self.assertEqual(report["approved_request_count"], 2)
        self.assertEqual(report["approved_total_cents"], 340_000)

    def test_draft_and_submitted_requests_are_not_counted(self):
        self._approved_request("Laptops", 250_000, MARCH)
        procurement_requests.create(
            self.conn,
            self.org.id,
            self.requester.id,
            self.supplier.id,
            "Still a draft",
            999_999,
            now=MARCH,
        )

        report = reporting_service.monthly_spend_report(self.conn, self.org.id, "2026-03")
        self.assertEqual(report["approved_request_count"], 1)
        self.assertEqual(report["approved_total_cents"], 250_000)
        self.assertEqual(
            [item["description"] for item in report["top_line_items"]], ["Laptops"]
        )

    def test_top_line_items_are_ranked_by_amount_and_limited(self):
        self._approved_request("Monitors", 90_000, MARCH)
        self._approved_request("Laptops", 250_000, MARCH)
        self._approved_request("Chairs", 120_000, MARCH)

        report = reporting_service.monthly_spend_report(
            self.conn, self.org.id, "2026-03", top_line_item_limit=2
        )
        self.assertEqual(
            [item["description"] for item in report["top_line_items"]],
            ["Laptops", "Chairs"],
        )
        self.assertEqual(
            [item["supplier_name"] for item in report["top_line_items"]],
            ["Office Supplies Ltd", "Office Supplies Ltd"],
        )
        self.assertEqual(report["top_line_items"][0]["currency"], "EUR")


if __name__ == "__main__":
    unittest.main()
