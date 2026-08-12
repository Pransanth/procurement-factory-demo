"""Repository for approval decisions on procurement requests.

Recording a decision is a small transaction: it validates that both the
request and the approver belong to the given organization, inserts the
approval row, and moves the request's status to 'approved' or 'rejected'.
"""

from datetime import datetime, timezone

from app.models import Approval
from app.repositories import procurement_requests, users


def _now():
    return datetime.now(timezone.utc).isoformat()


def _row_to_approval(row):
    return Approval(
        id=row["id"],
        organization_id=row["organization_id"],
        procurement_request_id=row["procurement_request_id"],
        approver_user_id=row["approver_user_id"],
        decision=row["decision"],
        comment=row["comment"],
        decided_at=row["decided_at"],
    )


def record_decision(
    conn, organization_id, procurement_request_id, approver_user_id, decision, comment=None, now=None
):
    request = procurement_requests.get_by_id(conn, organization_id, procurement_request_id)
    if request is None:
        raise ValueError(
            f"procurement request {procurement_request_id} not found in organization {organization_id}"
        )
    approver = users.get_by_id(conn, organization_id, approver_user_id)
    if approver is None:
        raise ValueError(
            f"approver {approver_user_id} not found in organization {organization_id}"
        )

    decided_at = now or _now()
    cursor = conn.execute(
        "INSERT INTO approvals "
        "(organization_id, procurement_request_id, approver_user_id, decision, comment, decided_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (organization_id, procurement_request_id, approver_user_id, decision, comment, decided_at),
    )
    conn.commit()

    procurement_requests.update_status(conn, organization_id, procurement_request_id, decision, now=decided_at)

    return get_by_id(conn, organization_id, cursor.lastrowid)


def get_by_id(conn, organization_id, approval_id):
    row = conn.execute(
        "SELECT * FROM approvals WHERE organization_id = ? AND id = ?",
        (organization_id, approval_id),
    ).fetchone()
    return _row_to_approval(row) if row else None


def list_for_request(conn, organization_id, procurement_request_id):
    rows = conn.execute(
        "SELECT * FROM approvals WHERE organization_id = ? AND procurement_request_id = ? ORDER BY id",
        (organization_id, procurement_request_id),
    ).fetchall()
    return [_row_to_approval(row) for row in rows]
