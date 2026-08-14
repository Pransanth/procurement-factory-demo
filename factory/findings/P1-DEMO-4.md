# P1-DEMO-4

Status: ANALYZED

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

Root Cause: app/services/reporting_service.py:monthly_spend_report() issues two hand-written SQL statements. The totals query (lines 29-34) binds the function's organization_id parameter into "WHERE organization_id = ? AND status = 'approved' AND created_at LIKE ?" and is therefore correctly tenant-scoped. The second query (lines 36-46), which collects the "top spend" line items, filters only on "pr.status = 'approved' AND pr.created_at LIKE ?" -- it contains no organization_id predicate at all, and the organization_id parameter is not among its bind values (line 45 binds only (month_prefix, top_line_item_limit)). organization_id is nevertheless accepted by the function and echoed back into the result dict (line 49), which makes the returned report look tenant-bound. The join to suppliers (line 41) is likewise unconstrained by tenant, so supplier_name for a foreign row is resolved and returned as well. Structurally the cause is that this module deliberately bypasses the repository layer -- where org scoping is enforced once per function -- and re-formulates its own SQL, and nothing in the codebase forces a hand-written service-layer query to carry the org predicate.
Affected Components: app/services/reporting_service.py (monthly_spend_report, exclusively the second/line-item query and its join to suppliers) and every consumer of the returned "top_line_items" list. Not affected: app/repositories/*.py (each read function scopes on organization_id per-function and is unchanged by this finding), app/services/procurement_service.py and app/services/user_admin_service.py (compose repositories, contain no raw SQL -- verified by grep for conn.execute across app/services/), app/jobs/* (reach data only through ScopedRepositories per P1-DEMO-1), app/db.py (the schema is correct: every tenant table carries organization_id NOT NULL; the gap is that one query never reads it).
Relevant Architecture: Tenant isolation in this codebase is enforced per repository function -- every function in app/repositories/*.py takes organization_id explicitly and puts it into its WHERE clause -- and app/test_multi_tenant_isolation.py verifies exactly that layer. app/services/reporting_service.py is the single deliberate exception: its module docstring states it issues its own SQL because reporting needs aggregation, ranking and joins that the repository layer intentionally does not expose. That exception is legitimate, but it moves the isolation obligation from a layer that enforces it structurally to a layer that has to remember it in every individual query string -- and there was no automated check anywhere that a hand-written service-layer query actually carries the predicate. The correctness of the first query and the incorrectness of the second in the same function is the direct consequence of that missing choke point.
Recommended Repair: Add the missing tenant predicate to the line-item query in app/services/reporting_service.py:monthly_spend_report(): "WHERE pr.organization_id = ? AND pr.status = 'approved' AND pr.created_at LIKE ?" with organization_id bound as the first parameter, and additionally constrain the joined suppliers row to the same tenant ("JOIN suppliers s ON s.id = pr.supplier_id AND s.organization_id = pr.organization_id") so no supplier name of another tenant can be resolved through the join even if a request ever referenced a foreign supplier id. No signature, return-shape or API change; the totals query stays as it is because it is already correct. In addition, and as the durable part of the repair, introduce the central guard described under Central Guard Plan so that the next hand-written query in this layer cannot silently omit the predicate.
Regression Test Plan: A new, dedicated regression file app/services/test_reporting_org_scope_regression.py, written and proven red against today's unmodified code. It builds two organizations with approved requests in the same month (mirroring the reproduction in the Befund section, including a foreign supplier named so it is unmistakable in output) and asserts: (1) top_line_items for Org A contains exclusively Org A's descriptions and exclusively Org A's supplier names -- today Org B's "B confidential tooling" / "B Secret Vendor" appear, so the assertion fails for exactly the security reason at stake; (2) the ranking/limit is computed inside the tenant, i.e. a larger foreign amount must not displace a smaller own line item out of the top-N list -- today the foreign item takes the top slot; (3) the already-correct headline totals remain unchanged (guarding against a "fix" that breaks the working query). The three assertions must be red before and green after the fix without any weakening. The existing app/services/test_reporting_service.py stays untouched and must remain green, since a correctly scoped query returns identical results for its single-tenant fixtures.
Central Guard Plan: A new deterministic AST guard, factory/guards/validate-service-sql-org-scope.py, wired as a fourth check into the canonical runner factory/guards/run-factory-checks.py (new --services-dir argument, default app/services, test_*.py excluded). For every SQL string literal passed to an .execute()/.executemany()/.executescript() call in a service module it determines which tenant-owned tables (users, suppliers, procurement_requests, approvals, audit_log, audit_log_archive, jobs) the statement references via its FROM/JOIN/UPDATE/DELETE clauses, and requires for each of them a predicate of the form <alias>.organization_id = ? (or, for a single unaliased table, organization_id = ?), or an equality against another referenced table's organization_id column for joined tables. The unfixed query in this finding is rejected by that rule, the fixed one passes -- both are pinned as fixtures in the guard's own unit tests (factory/guards/test_validate_service_sql_org_scope.py) and, so that CI genuinely exercises the new rule, as additional cases in factory/guards/test_run_factory_checks.py, which the CI workflow already runs. The guard itself runs in GitHub CI on every push/PR through the unchanged "Run canonical factory checks" step, because CI invokes exactly run-factory-checks.py; .github/workflows/factory-ci.yml is deliberately not modified.
Expected Blast Radius: The runtime change is one WHERE clause plus one join condition in a single read-only function; no schema change, no signature change, no write path, no other module. Every existing test in app/services/test_reporting_service.py is single-tenant and must return byte-identical results before and after, because adding a predicate that is already implicitly true for a single-tenant fixture changes nothing. The remaining behavioral change is precisely the intended one: a report for Org A no longer returns Org B's line items. The new guard is additive and affects no runtime code path; it currently applies to exactly one file containing raw SQL in app/services/ (reporting_service.py -- procurement_service.py and user_admin_service.py contain none) and passes on the fixed version.
Risk Assessment: Risk of the fix is low: additive predicate on a read-only query, confined to one function, no currently-passing test depends on the unscoped behavior, and the result shape is unchanged. The residual risk of the guard is a false positive on some future legitimate query (e.g. a genuinely cross-tenant admin report), which would surface as a failing deterministic check with a precise message and could then be reconsidered explicitly -- never silently. Risk of not fixing is a live, reproducible cross-tenant disclosure of procurement volumes and supplier relationships through a report that presents itself as tenant-bound, i.e. a confidentiality breach that is hard to notice precisely because the headline numbers are correct. This is a normal, autonomously decidable technical repair: bounded, reversible, and mirroring an isolation pattern already established everywhere else in the codebase.
Expert Review Reason: N/A
What Is Known: Not yet analyzed
What Remains Uncertain: Not yet analyzed
What An Expert Would Need To Review: Not yet analyzed
