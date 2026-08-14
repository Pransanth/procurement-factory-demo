"""Repository for users, scoped to a single organization.

Every function here requires an explicit organization_id and filters on it.
A lookup for a row that exists but belongs to a different organization
returns None rather than the row — callers cannot accidentally cross a
tenant boundary through this API.
"""

from datetime import datetime, timezone

from app.models import User


def _now():
    return datetime.now(timezone.utc).isoformat()


def _row_to_user(row):
    return User(
        id=row["id"],
        organization_id=row["organization_id"],
        email=row["email"],
        display_name=row["display_name"],
        role=row["role"],
        created_at=row["created_at"],
    )


def create(conn, organization_id, email, display_name, role, now=None):
    created_at = now or _now()
    cursor = conn.execute(
        "INSERT INTO users (organization_id, email, display_name, role, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (organization_id, email, display_name, role, created_at),
    )
    conn.commit()
    return get_by_id(conn, organization_id, cursor.lastrowid)


def get_by_id(conn, organization_id, user_id):
    row = conn.execute(
        "SELECT * FROM users WHERE organization_id = ? AND id = ?",
        (organization_id, user_id),
    ).fetchone()
    return _row_to_user(row) if row else None


def list_for_org(conn, organization_id):
    rows = conn.execute(
        "SELECT * FROM users WHERE organization_id = ? ORDER BY id", (organization_id,)
    ).fetchall()
    return [_row_to_user(row) for row in rows]


def update_role(conn, organization_id, user_id, role):
    """Set a user's role. Returns the updated User, or None if the id does
    not belong to this organization (nothing is written in that case)."""
    conn.execute(
        "UPDATE users SET role = ? WHERE organization_id = ? AND id = ?",
        (role, organization_id, user_id),
    )
    conn.commit()
    return get_by_id(conn, organization_id, user_id)
