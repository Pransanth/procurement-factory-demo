"""Orchestration layer for the procurement request lifecycle.

Repositories only know how to read/write their own table. This module
composes them for the multi-step operations a user actually performs
(create a request, submit it, approve or reject it) and records an audit
log entry for each step, all scoped to one organization.
"""

from app.repositories import approvals, audit_log, procurement_requests


def create_request(conn, organization_id, requested_by_user_id, supplier_id, description, amount_cents, currency="EUR"):
    request = procurement_requests.create(
        conn, organization_id, requested_by_user_id, supplier_id, description, amount_cents, currency
    )
    audit_log.record(
        conn,
        organization_id,
        action="procurement_request.created",
        entity_type="procurement_request",
        entity_id=request.id,
        actor_user_id=requested_by_user_id,
        details={"amount_cents": amount_cents, "currency": currency},
    )
    return request


def submit_request(conn, organization_id, request_id, actor_user_id):
    request = procurement_requests.get_by_id(conn, organization_id, request_id)
    if request is None:
        raise ValueError(f"procurement request {request_id} not found in organization {organization_id}")
    if request.status != "draft":
        raise ValueError(f"cannot submit request {request_id} from status '{request.status}'")

    updated = procurement_requests.update_status(conn, organization_id, request_id, "submitted")
    audit_log.record(
        conn,
        organization_id,
        action="procurement_request.submitted",
        entity_type="procurement_request",
        entity_id=request_id,
        actor_user_id=actor_user_id,
    )
    return updated


def decide_request(conn, organization_id, request_id, approver_user_id, decision, comment=None):
    request = procurement_requests.get_by_id(conn, organization_id, request_id)
    if request is None:
        raise ValueError(f"procurement request {request_id} not found in organization {organization_id}")
    if request.status != "submitted":
        raise ValueError(f"cannot decide on request {request_id} from status '{request.status}'")

    approval = approvals.record_decision(
        conn, organization_id, request_id, approver_user_id, decision, comment=comment
    )
    audit_log.record(
        conn,
        organization_id,
        action=f"procurement_request.{decision}",
        entity_type="procurement_request",
        entity_id=request_id,
        actor_user_id=approver_user_id,
        details={"comment": comment} if comment else None,
    )
    return approval
