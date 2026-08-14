"""Read-only reporting for finance/controlling.

Reports are aggregations over procurement data for one organization. Unlike
app/services/procurement_service.py, this module issues its own SQL instead
of composing app/repositories/*.py functions: a report needs aggregation and
ranking (COUNT, SUM, ORDER BY ... LIMIT, joins across tables) that the
repository layer deliberately does not expose — every function there returns
whole rows of exactly one table.

Every function here takes an explicit organization_id, the same argument
convention the repository layer uses.
"""

DEFAULT_TOP_LINE_ITEM_LIMIT = 5


def monthly_spend_report(
    conn, organization_id, month, top_line_item_limit=DEFAULT_TOP_LINE_ITEM_LIMIT
):
    """Approved procurement spend for one organization in one calendar month.

    `month` is an ISO year-month prefix such as "2026-03"; requests are
    attributed to the month they were created in. Returns a dict with the
    headline totals plus the largest individual approved requests, which the
    report renders as its "top spend" block.
    """
    month_prefix = f"{month}-%"

    totals_row = conn.execute(
        "SELECT COUNT(*) AS approved_count, COALESCE(SUM(amount_cents), 0) AS approved_cents "
        "FROM procurement_requests "
        "WHERE organization_id = ? AND status = 'approved' AND created_at LIKE ?",
        (organization_id, month_prefix),
    ).fetchone()

    line_item_rows = conn.execute(
        "SELECT pr.id AS request_id, pr.description AS description, "
        "pr.amount_cents AS amount_cents, pr.currency AS currency, "
        "s.name AS supplier_name "
        "FROM procurement_requests pr "
        "JOIN suppliers s ON s.id = pr.supplier_id "
        "WHERE pr.status = 'approved' AND pr.created_at LIKE ? "
        "ORDER BY pr.amount_cents DESC, pr.id ASC "
        "LIMIT ?",
        (month_prefix, top_line_item_limit),
    ).fetchall()

    return {
        "organization_id": organization_id,
        "month": month,
        "approved_request_count": totals_row["approved_count"],
        "approved_total_cents": totals_row["approved_cents"],
        "top_line_items": [
            {
                "request_id": row["request_id"],
                "description": row["description"],
                "amount_cents": row["amount_cents"],
                "currency": row["currency"],
                "supplier_name": row["supplier_name"],
            }
            for row in line_item_rows
        ],
    }
