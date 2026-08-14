# P1-DEMO-3

Status: OPEN

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

Root Cause: Not yet analyzed
Affected Components: Not yet analyzed
Relevant Architecture: Not yet analyzed
Recommended Repair: Not yet analyzed
Regression Test Plan: Not yet analyzed
Central Guard Plan: Not yet analyzed
Expected Blast Radius: Not yet analyzed
Risk Assessment: Not yet analyzed
Expert Review Reason: Not yet analyzed
What Is Known: Not yet analyzed
What Remains Uncertain: Not yet analyzed
What An Expert Would Need To Review: Not yet analyzed
