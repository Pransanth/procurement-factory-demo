"""Regression tests for finding P1-DEMO-4.

app/services/reporting_service.py:monthly_spend_report() computes its
headline totals with an organization-scoped query, but collected its
"top spend" line items with a query that filtered only on status and
month. A report requested for one organization therefore listed
descriptions, amounts and (through the join on suppliers) supplier names
belonging to other tenants, while its correct-looking totals hid that.

These tests are deliberately adversarial and cross-organization: they set
up a second tenant whose data must never appear in the first tenant's
report. They were written against the unfixed code and proven red there
(see factory/build-orders/P1-DEMO-4.md, "Red Regression Evidence").
"""

import unittest

from app.db import init_db
from app.repositories import organizations, procurement_requests, suppliers, users
from app.services import reporting_service

MARCH = "2026-03-05T09:00:00+00:00"


class TestMonthlySpendReportOrganizationScope(unittest.TestCase):
    def setUp(self):
        self.conn = init_db(":memory:")

        self.org_a = organizations.create(self.conn, "Org A")
        self.user_a = users.create(
            self.conn, self.org_a.id, "alice@a.example", "Alice", "member"
        )
        self.supplier_a = suppliers.create(self.conn, self.org_a.id, "A Supplies")

        self.org_b = organizations.create(self.conn, "Org B")
        self.user_b = users.create(self.conn, self.org_b.id, "bob@b.example", "Bob", "member")
        self.supplier_b = suppliers.create(self.conn, self.org_b.id, "B Secret Vendor")

    def _approved_request(self, org_id, user_id, supplier_id, description, amount_cents):
        request = procurement_requests.create(
            self.conn, org_id, user_id, supplier_id, description, amount_cents, now=MARCH
        )
        procurement_requests.update_status(self.conn, org_id, request.id, "approved", now=MARCH)
        return request

    def test_top_line_items_contain_no_foreign_organizations_data(self):
        self._approved_request(
            self.org_a.id, self.user_a.id, self.supplier_a.id, "A laptops", 10_000
        )
        self._approved_request(
            self.org_b.id,
            self.user_b.id,
            self.supplier_b.id,
            "B confidential tooling",
            900_000,
        )

        report = reporting_service.monthly_spend_report(self.conn, self.org_a.id, "2026-03")

        self.assertEqual(
            [item["description"] for item in report["top_line_items"]], ["A laptops"]
        )
        self.assertEqual(
            [item["supplier_name"] for item in report["top_line_items"]], ["A Supplies"]
        )

    def test_foreign_line_items_do_not_displace_own_items_from_the_top_list(self):
        self._approved_request(
            self.org_a.id, self.user_a.id, self.supplier_a.id, "A laptops", 10_000
        )
        self._approved_request(
            self.org_a.id, self.user_a.id, self.supplier_a.id, "A chairs", 5_000
        )
        self._approved_request(
            self.org_b.id,
            self.user_b.id,
            self.supplier_b.id,
            "B confidential tooling",
            900_000,
        )

        report = reporting_service.monthly_spend_report(
            self.conn, self.org_a.id, "2026-03", top_line_item_limit=2
        )

        self.assertEqual(
            [item["description"] for item in report["top_line_items"]],
            ["A laptops", "A chairs"],
        )

    def test_headline_totals_stay_scoped_to_the_requested_organization(self):
        self._approved_request(
            self.org_a.id, self.user_a.id, self.supplier_a.id, "A laptops", 10_000
        )
        self._approved_request(
            self.org_b.id,
            self.user_b.id,
            self.supplier_b.id,
            "B confidential tooling",
            900_000,
        )

        report = reporting_service.monthly_spend_report(self.conn, self.org_a.id, "2026-03")

        self.assertEqual(report["approved_request_count"], 1)
        self.assertEqual(report["approved_total_cents"], 10_000)


if __name__ == "__main__":
    unittest.main()
