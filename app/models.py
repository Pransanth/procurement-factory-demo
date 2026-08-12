"""Dataclasses mirroring the row shape of each table in app/db.py.

These are plain data containers built from sqlite3.Row objects by the
repository layer. They carry no behavior of their own.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Organization:
    id: int
    name: str
    created_at: str


@dataclass(frozen=True)
class User:
    id: int
    organization_id: int
    email: str
    display_name: str
    role: str
    created_at: str


@dataclass(frozen=True)
class Supplier:
    id: int
    organization_id: int
    name: str
    contact_email: Optional[str]
    created_at: str


@dataclass(frozen=True)
class ProcurementRequest:
    id: int
    organization_id: int
    requested_by_user_id: int
    supplier_id: int
    description: str
    amount_cents: int
    currency: str
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class Approval:
    id: int
    organization_id: int
    procurement_request_id: int
    approver_user_id: int
    decision: str
    comment: Optional[str]
    decided_at: str


@dataclass(frozen=True)
class AuditLogEntry:
    id: int
    organization_id: int
    occurred_at: str
    actor_user_id: Optional[int]
    action: str
    entity_type: str
    entity_id: Optional[int]
    details: Optional[str]


@dataclass(frozen=True)
class Job:
    id: int
    organization_id: int
    job_type: str
    payload: str
    status: str
    scheduled_for: Optional[str]
    created_at: str
    started_at: Optional[str]
    finished_at: Optional[str]
    result: Optional[str]
    error: Optional[str]
