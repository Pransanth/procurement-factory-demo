"""Repository for the append-only audit log, scoped to a single organization.

`actor_user_id` is nullable: background jobs write audit entries as the
"system", not as any particular user. `details` is stored as a JSON string
and handed back to callers as a dict.
"""

import json
from datetime import datetime, timezone

from app.models import AuditLogEntry


def _now():
    return datetime.now(timezone.utc).isoformat()


def _row_to_entry(row):
    return AuditLogEntry(
        id=row["id"],
        organization_id=row["organization_id"],
        occurred_at=row["occurred_at"],
        actor_user_id=row["actor_user_id"],
        action=row["action"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        details=row["details"],
    )


def record(
    conn,
    organization_id,
    action,
    entity_type,
    entity_id=None,
    actor_user_id=None,
    details=None,
    now=None,
):
    occurred_at = now or _now()
    details_json = json.dumps(details) if details is not None else None
    cursor = conn.execute(
        "INSERT INTO audit_log "
        "(organization_id, occurred_at, actor_user_id, action, entity_type, entity_id, details) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (organization_id, occurred_at, actor_user_id, action, entity_type, entity_id, details_json),
    )
    conn.commit()
    return get_by_id(conn, organization_id, cursor.lastrowid)


def get_by_id(conn, organization_id, entry_id):
    row = conn.execute(
        "SELECT * FROM audit_log WHERE organization_id = ? AND id = ?",
        (organization_id, entry_id),
    ).fetchone()
    return _row_to_entry(row) if row else None


def list_for_org(conn, organization_id):
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE organization_id = ? ORDER BY id", (organization_id,)
    ).fetchall()
    return [_row_to_entry(row) for row in rows]


def list_older_than(conn, organization_id, cutoff):
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE organization_id = ? AND occurred_at < ? ORDER BY id",
        (organization_id, cutoff),
    ).fetchall()
    return [_row_to_entry(row) for row in rows]


def archive_entries(conn, organization_id, entries, now=None):
    archived_at = now or _now()
    conn.executemany(
        "INSERT INTO audit_log_archive "
        "(id, organization_id, occurred_at, actor_user_id, action, entity_type, entity_id, "
        "details, archived_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                entry.id,
                organization_id,
                entry.occurred_at,
                entry.actor_user_id,
                entry.action,
                entry.entity_type,
                entry.entity_id,
                entry.details,
                archived_at,
            )
            for entry in entries
        ],
    )
    conn.commit()


def delete_ids(conn, organization_id, ids):
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    conn.execute(
        f"DELETE FROM audit_log WHERE organization_id = ? AND id IN ({placeholders})",
        (organization_id, *ids),
    )
    conn.commit()
