"""Administration of the users inside one organization.

Changing a user's role is an administrative operation on the tenant's own
user list. Like every state change in app/services/, it is recorded in the
audit log, and both the acting user and the target user are resolved through
the org-scoped user repository (app/repositories/users.py), so a user id
belonging to a different organization is simply not found.
"""

from app.repositories import audit_log, users

ASSIGNABLE_ROLES = ("member", "approver", "admin")

# Which roles may administer other users' roles. This is an allowlist, not a
# denylist, on purpose: naming who may act keeps a newly added role
# unprivileged by default, whereas naming who may not act silently grants
# authority to every role nobody thought to exclude (finding P1-DEMO-5).
# 'approver' decides procurement requests (app/repositories/approvals.py); it
# is not administrative.
ROLE_ADMINISTERING_ROLES = ("admin",)


def change_user_role(conn, organization_id, actor_user_id, target_user_id, new_role):
    """Set `target_user_id`'s role to `new_role` on behalf of `actor_user_id`.

    Returns the updated User. Raises ValueError if the role is not
    assignable, if either user does not belong to `organization_id`, or if
    the acting user is not permitted to administer roles.
    """
    if new_role not in ASSIGNABLE_ROLES:
        raise ValueError(
            f"role '{new_role}' is not assignable (allowed: {', '.join(ASSIGNABLE_ROLES)})"
        )

    actor = users.get_by_id(conn, organization_id, actor_user_id)
    if actor is None:
        raise ValueError(f"actor {actor_user_id} not found in organization {organization_id}")

    if actor.role not in ROLE_ADMINISTERING_ROLES:
        raise ValueError(
            f"user {actor_user_id} has role '{actor.role}' and is not authorized to "
            "administer user roles"
        )

    target = users.get_by_id(conn, organization_id, target_user_id)
    if target is None:
        raise ValueError(f"user {target_user_id} not found in organization {organization_id}")

    updated = users.update_role(conn, organization_id, target_user_id, new_role)
    audit_log.record(
        conn,
        organization_id,
        action="user.role_changed",
        entity_type="user",
        entity_id=target_user_id,
        actor_user_id=actor_user_id,
        details={"from_role": target.role, "to_role": new_role},
    )
    return updated
