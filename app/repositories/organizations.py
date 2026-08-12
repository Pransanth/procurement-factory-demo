"""Repository for organizations — the tenants themselves.

Organizations are the one table that is *not* organization-scoped: there is
no parent org to filter by. Every other repository in app/repositories/
requires an explicit organization_id argument; this one does not, by
design.
"""

from datetime import datetime, timezone

from app.models import Organization


def _now():
    return datetime.now(timezone.utc).isoformat()


def _row_to_organization(row):
    return Organization(id=row["id"], name=row["name"], created_at=row["created_at"])


def create(conn, name, now=None):
    created_at = now or _now()
    cursor = conn.execute(
        "INSERT INTO organizations (name, created_at) VALUES (?, ?)",
        (name, created_at),
    )
    conn.commit()
    return get_by_id(conn, cursor.lastrowid)


def get_by_id(conn, organization_id):
    row = conn.execute(
        "SELECT * FROM organizations WHERE id = ?", (organization_id,)
    ).fetchone()
    return _row_to_organization(row) if row else None


def get_by_name(conn, name):
    row = conn.execute("SELECT * FROM organizations WHERE name = ?", (name,)).fetchone()
    return _row_to_organization(row) if row else None


def list_all(conn):
    rows = conn.execute("SELECT * FROM organizations ORDER BY id").fetchall()
    return [_row_to_organization(row) for row in rows]
