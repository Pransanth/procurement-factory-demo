"""Repository for procurement requests, scoped to a single organization."""

from datetime import datetime, timezone

from app.models import ProcurementRequest
from app.repositories import suppliers


def _now():
    return datetime.now(timezone.utc).isoformat()


def _row_to_request(row):
    return ProcurementRequest(
        id=row["id"],
        organization_id=row["organization_id"],
        requested_by_user_id=row["requested_by_user_id"],
        supplier_id=row["supplier_id"],
        description=row["description"],
        amount_cents=row["amount_cents"],
        currency=row["currency"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def create(
    conn,
    organization_id,
    requested_by_user_id,
    supplier_id,
    description,
    amount_cents,
    currency="EUR",
    now=None,
):
    if suppliers.get_by_id(conn, organization_id, supplier_id) is None:
        raise ValueError(
            f"supplier {supplier_id} not found in organization {organization_id}"
        )

    timestamp = now or _now()
    cursor = conn.execute(
        "INSERT INTO procurement_requests "
        "(organization_id, requested_by_user_id, supplier_id, description, amount_cents, "
        "currency, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?)",
        (
            organization_id,
            requested_by_user_id,
            supplier_id,
            description,
            amount_cents,
            currency,
            timestamp,
            timestamp,
        ),
    )
    conn.commit()
    return get_by_id(conn, organization_id, cursor.lastrowid)


def get_by_id(conn, organization_id, request_id):
    row = conn.execute(
        "SELECT * FROM procurement_requests WHERE organization_id = ? AND id = ?",
        (organization_id, request_id),
    ).fetchone()
    return _row_to_request(row) if row else None


def list_for_org(conn, organization_id):
    rows = conn.execute(
        "SELECT * FROM procurement_requests WHERE organization_id = ? ORDER BY id",
        (organization_id,),
    ).fetchall()
    return [_row_to_request(row) for row in rows]


def update_status(conn, organization_id, request_id, status, now=None):
    timestamp = now or _now()
    conn.execute(
        "UPDATE procurement_requests SET status = ?, updated_at = ? "
        "WHERE organization_id = ? AND id = ?",
        (status, timestamp, organization_id, request_id),
    )
    conn.commit()
    return get_by_id(conn, organization_id, request_id)


def list_pending_older_than(conn, organization_id, cutoff):
    """Submitted requests (still awaiting a decision) last updated before `cutoff`."""
    rows = conn.execute(
        "SELECT * FROM procurement_requests "
        "WHERE organization_id = ? AND status = 'submitted' AND updated_at < ? "
        "ORDER BY id",
        (organization_id, cutoff),
    ).fetchall()
    return [_row_to_request(row) for row in rows]
