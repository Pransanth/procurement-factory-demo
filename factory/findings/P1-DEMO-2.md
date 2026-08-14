# P1-DEMO-2

Status: IMPLEMENTING

## Befund

Beim Anlegen einer Procurement-Anfrage (`app/repositories/procurement_requests.py:create`,
aufgerufen u. a. über `app/services/procurement_service.py:create_request`) wird die übergebene
`supplier_id` nicht dagegen geprüft, ob der referenzierte Supplier tatsächlich zur angegebenen
`organization_id` gehört. Das Datenbankschema (`app/db.py`) erzwingt für
`procurement_requests.supplier_id` nur `REFERENCES suppliers(id)`, also lediglich Existenz der
Zeile, nicht Zugehörigkeit zur selben Organisation.

Reproduktion (gegen eine frische In-Memory-DB via `app/db.py:init_db`):

```python
from app.db import init_db
from app.repositories import organizations, users, suppliers, procurement_requests

conn = init_db(":memory:")
org_a = organizations.create(conn, "Org A")
org_b = organizations.create(conn, "Org B")

user_a = users.create(conn, org_a.id, "alice@a.example", "Alice", "member")
supplier_b = suppliers.create(conn, org_b.id, "B Supplies (secret vendor)")

req = procurement_requests.create(conn, org_a.id, user_a.id, supplier_b.id, "sneaky", 50000)
# req.organization_id == org_a.id, aber req.supplier_id == supplier_b.id (gehört zu Org B).
# Kein Fehler, keine Ablehnung -- die Anfrage wird klaglos angelegt.
```

Der resultierende Datensatz gehört laut `organization_id` zu Org A, verweist aber über
`supplier_id` auf einen Supplier von Org B. Das bestehende Isolationstestset
(`app/test_multi_tenant_isolation.py`) deckt diesen Fall nicht ab -- es prüft nur, dass Lesezugriffe
über die Repository-Funktionen korrekt gescoped sind, nicht, dass beim *Schreiben* eine fremde
Organisation referenziert werden kann.

Dies betrifft einen anderen Codepfad als P1-DEMO-1 (dort: Job-Handler-Payload vs. hier:
Request-Erstellung im interaktiven Pfad `app/services/procurement_service.py` /
`app/repositories/procurement_requests.py`) und ist unabhängig von P1-DEMO-3.

## Analyse

Root Cause: app/repositories/procurement_requests.py:create() inserts a procurement_requests row with a caller-supplied supplier_id and organization_id without ever checking that the referenced supplier actually belongs to that organization_id; app/db.py only declares supplier_id INTEGER NOT NULL REFERENCES suppliers(id), which SQLite enforces as "this row id exists in suppliers", not "this row id belongs to organization_id". Unlike app/repositories/approvals.py:record_decision (lines 33-43), which explicitly re-fetches both the request and the approver scoped to organization_id and raises ValueError if either lookup returns None, procurement_requests.create() performs no such cross-reference check for supplier_id before inserting. app/services/procurement_service.py:create_request (line 12-15) calls procurement_requests.create() directly and adds no additional validation of its own, so the gap is present on the only production call path.
Affected Components: app/repositories/procurement_requests.py (create), app/services/procurement_service.py (create_request, the only production caller), app/repositories/suppliers.py (get_by_id, the org-scoped lookup that needs to be consulted); not affected: app/repositories/approvals.py (already validates its own cross-references correctly), app/jobs/* (background jobs do not create procurement requests), app/db.py (no schema change needed or made).
Relevant Architecture: Every repository under app/repositories/*.py enforces tenant isolation the same way: every read/write takes an explicit organization_id and filters/checks against it (see app/repositories/users.py, app/repositories/suppliers.py). This is a convention enforced per-function, not a structural guarantee -- there is no single choke point that validates a foreign-key-style reference (supplier_id, requested_by_user_id, etc.) against the same organization_id before a write happens; each repository function is individually responsible for calling the right org-scoped lookup for every foreign id it accepts. procurement_requests.create() accepts both requested_by_user_id and supplier_id as foreign references but only supplier_id is unchecked -- requested_by_user_id is not separately validated either, but it is out of scope for this finding (see Befund) since P1-DEMO-2 is specifically about the supplier reference as reproduced above; the same class of gap for requested_by_user_id would need its own finding if a concrete gap is confirmed there.
Recommended Repair: Add an explicit cross-organization check inside app/repositories/procurement_requests.py:create(), mirroring the existing pattern already used in app/repositories/approvals.py:record_decision -- call suppliers.get_by_id(conn, organization_id, supplier_id) before the INSERT and raise ValueError (same exception type and "not found in organization" phrasing already used elsewhere in this codebase) if it returns None. Placing the check in the repository function (not only in the service layer) makes it the structural choke point for every current and future caller of procurement_requests.create(), consistent with how record_decision already protects its own callers regardless of what the service layer does.
Regression Test Plan: A new regression test (mirroring app/jobs/test_org_scope_regression.py's structure for P1-DEMO-1) must, against today's unmodified code, construct two organizations, create a supplier under Org B, and call procurement_requests.create() for Org A referencing Org B's supplier_id directly -- and assert this raises ValueError. Today's code performs the insert instead of raising, so the test is red for the correct reason (the created row silently has organization_id == org_a.id and supplier_id pointing at Org B's supplier, exactly as reproduced in the Befund section above). After the fix, the same call must raise ValueError with no row inserted; the assertion is not weakened, only the observed behavior changes from "silently succeeds" to "raises".
Central Guard Plan: This is a runtime data-validation gap, not a bypassable structural API surface (unlike P1-DEMO-1's job-handler payload), so the proportionate central guard is not a new bespoke AST script but the deterministic, always-on regression suite the factory already treats as a canonical gate: factory/guards/run-app-tests.py auto-discovers every app/**/test_*.py file (no manual registration needed) and is run by GitHub CI (.github/workflows/factory-ci.yml, "Run application test suite" step) on every push/PR to main. The new regression test becomes a permanent member of that auto-discovered suite the moment its file exists under app/, so any future change that reintroduces the unchecked supplier_id path (e.g. someone removing the new suppliers.get_by_id check during a refactor) breaks this central, always-executed gate immediately rather than depending on a developer remembering to test the cross-org case by hand.
Expected Blast Radius: The fix only adds a new validation branch to procurement_requests.create() that raises ValueError in a case that today already silently produces an inconsistent, unusable row (a request whose supplier does not belong to its own organization) -- no currently-correct caller passes a cross-org supplier_id, since app/services/test_procurement_service.py and app/repositories/test_procurement_requests.py only ever construct same-organization suppliers today, so no legitimate call site is affected. The change is additive and confined to app/repositories/procurement_requests.py (plus the new suppliers import) and app/services/procurement_service.py is unaffected since it does not need to catch or translate the new ValueError itself (record_decision's pre-existing ValueError from cross-org checks already propagates the same way).
Risk Assessment: Risk of the fix is low: it is additive, mirrors an already-proven-correct pattern in the same codebase (approvals.record_decision), touches no schema, and does not change behavior for any currently-passing test or legitimate call path -- only for a call path that produces a security-relevant, inconsistent data state today. Risk of not fixing it is a real, currently-exploitable multi-tenant boundary violation in the interactive path: any authenticated user of Org A can, if they can supply an arbitrary supplier_id in the request-creation call, cause a procurement_requests row that names a supplier belonging to a different organization -- confirmed by the reproduction in the Befund section, not merely theoretical. This is a normal, autonomously resolvable technical decision: bounded scope, proven pattern, no irreversible consequence.
Expert Review Reason: N/A
What Is Known: N/A
What Remains Uncertain: N/A
What An Expert Would Need To Review: N/A
