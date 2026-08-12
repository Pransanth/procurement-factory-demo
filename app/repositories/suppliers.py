"""Repository for suppliers, scoped to a single organization.

Same org-scoping pattern as app/repositories/users.py: every function
requires an explicit organization_id, and a lookup for a row belonging to a
different organization returns None.
"""

from datetime import datetime, timezone

from app.models import Supplier


def _now():
    return datetime.now(timezone.utc).isoformat()


def _row_to_supplier(row):
    return Supplier(
        id=row["id"],
        organization_id=row["organization_id"],
        name=row["name"],
        contact_email=row["contact_email"],
        created_at=row["created_at"],
    )


def create(conn, organization_id, name, contact_email=None, now=None):
    created_at = now or _now()
    cursor = conn.execute(
        "INSERT INTO suppliers (organization_id, name, contact_email, created_at) "
        "VALUES (?, ?, ?, ?)",
        (organization_id, name, contact_email, created_at),
    )
    conn.commit()
    return get_by_id(conn, organization_id, cursor.lastrowid)


def get_by_id(conn, organization_id, supplier_id):
    row = conn.execute(
        "SELECT * FROM suppliers WHERE organization_id = ? AND id = ?",
        (organization_id, supplier_id),
    ).fetchone()
    return _row_to_supplier(row) if row else None


def list_for_org(conn, organization_id):
    rows = conn.execute(
        "SELECT * FROM suppliers WHERE organization_id = ? ORDER BY id", (organization_id,)
    ).fetchall()
    return [_row_to_supplier(row) for row in rows]
