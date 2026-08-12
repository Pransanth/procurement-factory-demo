"""Schema and connection setup for the dummy procurement app.

Usage:
    from app.db import init_db
    conn = init_db(":memory:")   # or a filesystem path

Every table except `organizations` itself carries an `organization_id`
column used by the repository layer to scope reads and writes to a single
tenant. Foreign keys are enforced (PRAGMA foreign_keys = ON) so that a bad
reference fails loudly instead of silently.
"""

import sqlite3

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('member', 'approver', 'admin')),
    created_at TEXT NOT NULL,
    UNIQUE(organization_id, email)
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    name TEXT NOT NULL,
    contact_email TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(organization_id, name)
);

CREATE TABLE IF NOT EXISTS procurement_requests (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    requested_by_user_id INTEGER NOT NULL REFERENCES users(id),
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    description TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    currency TEXT NOT NULL DEFAULT 'EUR',
    status TEXT NOT NULL CHECK(status IN ('draft', 'submitted', 'approved', 'rejected')) DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    procurement_request_id INTEGER NOT NULL REFERENCES procurement_requests(id),
    approver_user_id INTEGER NOT NULL REFERENCES users(id),
    decision TEXT NOT NULL CHECK(decision IN ('approved', 'rejected')),
    comment TEXT,
    decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    occurred_at TEXT NOT NULL,
    actor_user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    details TEXT
);

CREATE TABLE IF NOT EXISTS audit_log_archive (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    occurred_at TEXT NOT NULL,
    actor_user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    details TEXT,
    archived_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    job_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'succeeded', 'failed')) DEFAULT 'pending',
    scheduled_for TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    result TEXT,
    error TEXT
);
"""


def init_db(path=":memory:"):
    """Create a connection with the full schema applied and FKs enforced."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
