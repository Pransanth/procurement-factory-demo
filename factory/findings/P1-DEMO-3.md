# P1-DEMO-3

Status: IMPLEMENTING

## Befund

Die Entscheidung über eine Procurement-Anfrage (`app/repositories/approvals.py:record_decision`,
aufgerufen u. a. über `app/services/procurement_service.py:decide_request`) prüft zwar, dass
sowohl die Anfrage als auch der entscheidende Nutzer zur angegebenen `organization_id` gehören,
nicht aber, welche `role` dieser Nutzer hat. Das Datenmodell kennt drei Rollen
(`app/db.py`: `role TEXT NOT NULL CHECK(role IN ('member', 'approver', 'admin'))`), aber an
keiner Stelle im Entscheidungspfad wird geprüft, dass nur `approver` oder `admin` eine Anfrage
genehmigen oder ablehnen dürfen.

Reproduktion (gegen eine frische In-Memory-DB via `app/db.py:init_db`):

```python
from app.db import init_db
from app.repositories import organizations, users, suppliers
from app.services import procurement_service

conn = init_db(":memory:")
org_a = organizations.create(conn, "Org A")

member = users.create(conn, org_a.id, "mallory@a.example", "Mallory", "member")
supplier = suppliers.create(conn, org_a.id, "A Supplies")

req = procurement_service.create_request(conn, org_a.id, member.id, supplier.id, "big purchase", 99999900)
procurement_service.submit_request(conn, org_a.id, req.id, member.id)

# Mallory hat die Rolle 'member', keine 'approver'/'admin' -- entscheidet trotzdem über
# ihre eigene Anfrage, ohne dass irgendetwas das ablehnt:
approval = procurement_service.decide_request(conn, org_a.id, req.id, member.id, "approved")
# approval.decision == "approved"
```

Das bestehende Testset `app/test_multi_tenant_isolation.py::test_approvals_cannot_cross_organizations`
prüft nur die Organisationsgrenze (fremde Org-ID wird abgelehnt), nicht die Rollengrenze innerhalb
derselben Organisation. Ebenso wenig geprüft: dass ein Nutzer über die eigene, selbst gestellte
Anfrage entscheidet (Self-Approval).

Dies betrifft einen anderen Codepfad als P1-DEMO-1 (Job-Scoping) und als P1-DEMO-2
(Supplier-Referenz bei Request-Erstellung) -- hier geht es um serverseitige Rollen-/
Berechtigungsdurchsetzung beim Entscheidungsschritt, nicht um Organisationszugehörigkeit von
Datensätzen. Unabhängig von P1-DEMO-2.

## Analyse

Root Cause: app/repositories/approvals.py:record_decision() validates that the procurement_request and the approver both belong to organization_id (lines 33-42, raising ValueError otherwise), but never checks the approver's role, and never checks that the approver is not the same user who created the request being decided. app/db.py declares users.role TEXT NOT NULL CHECK(role IN ('member', 'approver', 'admin')) at the schema level, so the three roles exist and are enforced as valid values, but nothing in the decision path (record_decision, nor its only caller app/services/procurement_service.py:decide_request, lines 47-66) ever reads or checks that column's value before allowing a decision. The same gap applies to self-approval: decide_request never compares approver_user_id to the request's own requested_by_user_id.
Affected Components: app/repositories/approvals.py (record_decision), app/services/procurement_service.py (decide_request, the only production caller); not affected: app/repositories/procurement_requests.py (already fixed independently in P1-DEMO-2, no overlap -- that fix validates supplier_id at creation time, this finding is about the decision step), app/jobs/* (background jobs do not decide requests), app/db.py (the role CHECK constraint already exists and is correct; the gap is that its value is never read on this path, not that the constraint itself is wrong).
Relevant Architecture: Every repository under app/repositories/*.py enforces organization isolation per-function (see [[P1-DEMO-2]]'s finding for the same architectural observation), but role-based authorization is a separate concern from organization isolation and has no enforcement point anywhere in the codebase today -- app/repositories/users.py exposes the role column via get_by_id/list_for_org like any other field, but no caller anywhere (repository or service layer) ever branches on its value. record_decision already does the right kind of check for the two dimensions it does cover (request org membership, approver org membership); role and self-approval are simply two additional dimensions of the same "is this actor allowed to do this to this data" question that were never added.
Recommended Repair: Extend app/repositories/approvals.py:record_decision() with two additional checks, placed after the existing org-membership checks and before the INSERT: (1) re-fetch the approver's role (already available on the `approver` object returned by users.get_by_id, no extra query needed) and raise ValueError if it is not in {'approver', 'admin'}; (2) raise ValueError if approver_user_id == request.requested_by_user_id (self-approval), regardless of role -- even an admin must not approve their own request, since self-approval is a control-integrity problem independent of role sufficiency. Both checks belong in the repository function (not only the service layer), for the same reason as P1-DEMO-2: it is the single choke point every current and future caller goes through.
Regression Test Plan: Two new regression tests (or two assertions in one dedicated regression test file), against today's unmodified code: (1) construct a request in Org A, submit it, and call decide_request with an approver whose role is 'member' -- assert this raises ValueError; today it succeeds and returns an 'approved' Approval, exactly as reproduced in the Befund section. (2) construct a request in Org A created by user X with role 'approver', submit it, and call decide_request with approver_user_id == X's own id -- assert this raises ValueError; today it succeeds even though X is deciding on their own request. Both must be red for the correct reason (a returned successful Approval with the wrong decision outcome, not an unrelated error) and green after the fix without weakening either assertion.
Central Guard Plan: Same reasoning as [[P1-DEMO-2]]: this is a runtime authorization-validation gap in a single repository function, not a bypassable structural API surface, so the proportionate central guard is not a new bespoke AST script but the deterministic, always-on regression suite the factory already treats as a canonical gate -- factory/guards/run-app-tests.py auto-discovers every app/**/test_*.py file with no manual registration, and GitHub CI (.github/workflows/factory-ci.yml, "Run application test suite" step) runs it on every push/PR to main. The two new regression tests become permanent members of that suite the moment their file exists, so a future refactor that drops the role or self-approval check breaks this always-executed gate immediately.
Expected Blast Radius: The fix adds two new validation branches to record_decision() that raise ValueError in cases that today already produce a security-relevant, incorrect outcome (a request approved/rejected by someone unauthorized to do so) -- no currently-passing test exercises a 'member'-role or self-approving decider, since app/repositories/test_approvals.py, app/services/test_procurement_service.py and app/test_multi_tenant_isolation.py only ever use 'approver' or 'admin' role users who are not the requester for their approve/reject assertions today. The change is additive and confined to app/repositories/approvals.py; app/services/procurement_service.py needs no change since it already propagates ValueError from record_decision unmodified (see its existing handling of the org-membership ValueErrors from the same function).
Risk Assessment: Risk of the fix is low: additive, confined to one function, and does not change behavior for any currently-passing test or legitimate call path -- every existing test already uses an authorized, non-self decider. Risk of not fixing it is a real, currently-exploitable authorization boundary violation in the interactive path: any authenticated 'member' can approve or reject any submitted request in their own organization including their own, confirmed by the reproduction in the Befund section (Mallory, role 'member', approves her own 99999900-cent request), not merely theoretical. This is a normal, autonomously resolvable technical decision: bounded scope, mirrors the already-established validation pattern in the same function, no irreversible consequence.
Expert Review Reason: N/A
What Is Known: N/A
What Remains Uncertain: N/A
What An Expert Would Need To Review: N/A
