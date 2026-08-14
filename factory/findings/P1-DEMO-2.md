# P1-DEMO-2

Status: OPEN

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
