# P1-DEMO-4

Status: OPEN

## Befund

Der Monatsbericht `app/services/reporting_service.py:monthly_spend_report` liefert im Feld
`top_line_items` Positionen fremder Organisationen aus. Die Kopfzahlen des Berichts
(`approved_request_count`, `approved_total_cents`) werden mit einer Abfrage ermittelt, die auf
`organization_id` filtert; die zweite Abfrage, die die größten genehmigten Einzelpositionen für den
"Top Spend"-Block einsammelt, filtert dagegen nur auf `status = 'approved'` und den Monat. Der
Bericht ist dadurch in seinen Summen korrekt tenant-gebunden, in seiner Detailliste aber nicht —
die Korrektheit der Kopfzahlen verdeckt den Fehler in der Detailliste.

Ausgeliefert werden dabei `description`, `amount_cents`, `currency` und (über den Join auf
`suppliers`) `supplier_name` fremder Organisationen, also Beschaffungsvolumen und
Lieferantenbeziehungen anderer Mandanten.

Reproduktion (gegen eine frische In-Memory-DB via `app/db.py:init_db`):

```python
from app.db import init_db
from app.repositories import organizations, procurement_requests, suppliers, users
from app.services import reporting_service

conn = init_db(":memory:")
org_a = organizations.create(conn, "Org A")
org_b = organizations.create(conn, "Org B")

user_a = users.create(conn, org_a.id, "alice@a.example", "Alice", "member")
supplier_a = suppliers.create(conn, org_a.id, "A Supplies")
user_b = users.create(conn, org_b.id, "bob@b.example", "Bob", "member")
supplier_b = suppliers.create(conn, org_b.id, "B Secret Vendor")

march = "2026-03-05T09:00:00+00:00"
req_a = procurement_requests.create(conn, org_a.id, user_a.id, supplier_a.id, "A laptops", 10_000, now=march)
procurement_requests.update_status(conn, org_a.id, req_a.id, "approved", now=march)
req_b = procurement_requests.create(conn, org_b.id, user_b.id, supplier_b.id, "B confidential tooling", 900_000, now=march)
procurement_requests.update_status(conn, org_b.id, req_b.id, "approved", now=march)

report = reporting_service.monthly_spend_report(conn, org_a.id, "2026-03")
# report["approved_request_count"] == 1 und report["approved_total_cents"] == 10000 -- korrekt fuer Org A.
# report["top_line_items"] enthaelt aber zusaetzlich
#   {"description": "B confidential tooling", "amount_cents": 900000, "supplier_name": "B Secret Vendor", ...}
#   -- eine Position, die Org B gehoert.
```

Das bestehende Testset zu diesem Modul (`app/services/test_reporting_service.py`) deckt den Fall
nicht ab: es richtet nur eine einzige Organisation ein und prüft Summen, Ranking und Limit
innerhalb dieses einen Mandanten. Auch `app/test_multi_tenant_isolation.py` erfasst ihn nicht — dort
werden ausschließlich die Repository-Lesefunktionen geprüft, nicht der Reporting-Pfad, der seine
Abfragen an der Repository-Schicht vorbei selbst formuliert.

Dies betrifft einen anderen Codepfad als P1-DEMO-1 (Job-Handler), P1-DEMO-2 (Anlegen einer
Anfrage) und P1-DEMO-3 (Entscheidungspfad) und ist unabhängig von P1-DEMO-5.

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
