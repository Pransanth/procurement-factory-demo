# Bauauftrag: P1-DEMO-4

Bezug: [`factory/findings/P1-DEMO-4.md`](../findings/P1-DEMO-4.md) (Status: `ANALYZED`)

Dieser Bauauftrag legt fest, **was** in der nächsten Phase (`IMPLEMENTING`) gebaut werden darf,
in welcher Reihenfolge, und woran Erfolg gemessen wird.

## Primäre Sicherheitsgrenze

Die primäre Sicherheitsgrenze ist die Abfrage selbst: die Line-Item-Abfrage in
`app/services/reporting_service.py:monthly_spend_report()` muss den Mandanten im
`WHERE`-Ausdruck führen, gebunden an den `organization_id`-Parameter der Funktion:

1. **Tenant-Prädikat**: `WHERE pr.organization_id = ?` als erste Bedingung, `organization_id`
   als erster Bind-Parameter.
2. **Tenant-gebundener Join**: `JOIN suppliers s ON s.id = pr.supplier_id AND s.organization_id
   = pr.organization_id`, damit auch der über den Join gelesene `supplier_name` keinen fremden
   Mandanten auflösen kann.

Die Kopfzahlen-Abfrage bleibt unverändert — sie ist bereits korrekt gescoped und darf durch die
Reparatur nicht beschädigt werden.

Die **zusätzliche**, dauerhafte Schranke ist der neue AST-Guard
`factory/guards/validate-service-sql-org-scope.py` (siehe "Central Guard"). Er ist ausdrücklich
nicht die Sicherheitsgrenze selbst — die ist das Prädikat in der Abfrage —, sondern verhindert,
dass die nächste handgeschriebene Service-Abfrage sie erneut vergisst.

## Verbindliche Reihenfolge

1. **Regressionstest zuerst, gegen den heutigen Code.** Zwei Organisationen mit genehmigten
   Anfragen im selben Monat; Assertions gemäß Regression Test Plan des Findings.
2. **Der Test muss aus dem fachlich richtigen Grund rot sein**: die fremde Position
   (`B confidential tooling` / `B Secret Vendor`) erscheint in `top_line_items` von Org A und
   verdrängt zusätzlich die eigene Position aus der Top-N-Liste — kein Import-, Namens- oder
   Syntaxfehler.
3. **Erst danach**: Implementierung des Prädikats und des tenant-gebundenen Joins.
4. **Erst danach**: Bestätigen, dass die Regressionstests jetzt grün sind, ohne die
   Kernassertionen abzuschwächen, und dass `app/services/test_reporting_service.py` unverändert
   grün bleibt.
5. **Erst danach**: den zentralen Guard bauen, samt eigener Tests, und in den kanonischen Runner
   einhängen.

## Acceptance Criteria

1. Die neuen Regressionstests sind gegen den heutigen Code nachweislich rot, aus dem fachlich
   richtigen Grund.
2. Dieselben Regressionstests sind nach dem Fix grün, mit unveränderten Kernassertionen.
3. `app/services/test_reporting_service.py` bleibt unverändert grün (Single-Tenant-Ergebnisse
   sind identisch).
4. `app/test_multi_tenant_isolation.py` bleibt grün.
5. Der neue Guard weist die **unreparierte** Abfrage zurück und akzeptiert die reparierte —
   beides als Fixture in seinen eigenen Tests festgehalten.
6. Alle App-Tests sind grün (`python3 factory/guards/run-app-tests.py`).
7. Alle Factory-Guard-Tests sind grün, inklusive der erweiterten
   `factory.guards.test_run_factory_checks`.
8. `python3 factory/guards/run-factory-checks.py` beendet sich mit Exit-Code 0.

## Scope

**Erlaubt:**
- Änderung ausschließlich an der Line-Item-Abfrage in `app/services/reporting_service.py`
  (Prädikat + Join-Bedingung + Bind-Parameter, kein Signatur- oder Rückgabewechsel).
- Neue Testdatei `app/services/test_reporting_org_scope_regression.py`.
- Neuer Guard `factory/guards/validate-service-sql-org-scope.py` und dessen Testdatei
  `factory/guards/test_validate_service_sql_org_scope.py`.
- Einhängen des Guards in `factory/guards/run-factory-checks.py` (neues `--services-dir`,
  Default `app/services`, `test_*.py` ausgenommen) und entsprechende Ergänzung von
  `factory/guards/test_run_factory_checks.py`.

**Nicht erlaubt / außerhalb dieses Bauauftrags:**
- Keine Änderung an der bereits korrekten Kopfzahlen-Abfrage.
- Keine Änderung an `app/repositories/*`, `app/jobs/*`, `app/db.py`, `app/services/procurement_service.py`,
  `app/services/user_admin_service.py` — P1-DEMO-5 wird getrennt bearbeitet und darf hier nicht
  angefasst werden.
- Keine Änderung an bestehenden Tests (weder Abschwächung noch Anpassung von
  `app/services/test_reporting_service.py`).
- Keine Änderung an `.github/workflows/factory-ci.yml`, `factory/README.md`, `CLAUDE.md` oder an
  Permissions/Sandbox/Hooks — außerhalb des Schreib-Scopes dieses Laufs. Der neue Guard erreicht
  CI ohne Workflow-Änderung, weil CI ohnehin `run-factory-checks.py` aufruft; seine Detektion
  wird zusätzlich über `factory.guards.test_run_factory_checks` in CI mitgeprüft.

## Central Guard

`factory/guards/validate-service-sql-org-scope.py`, deterministisch, ohne KI, ohne Netzwerk:

- Prüft eine einzelne `.py`-Datei aus der Service-Schicht.
- Sammelt per AST alle String-Literale, die als erstes Argument an `.execute()`,
  `.executemany()` oder `.executescript()` übergeben werden.
- Ermittelt je Statement die referenzierten mandantengebundenen Tabellen (`users`, `suppliers`,
  `procurement_requests`, `approvals`, `audit_log`, `audit_log_archive`, `jobs`) aus
  `FROM`/`JOIN`/`UPDATE`/`INSERT INTO`/`DELETE FROM` samt Alias.
- Verlangt für jede referenzierte Tabelle ein `organization_id`-Prädikat: `<alias>.organization_id = ?`
  bzw. bei genau einer, nicht aliasierten Tabelle auch `organization_id = ?`; für über einen Join
  hinzugekommene Tabellen alternativ die Gleichsetzung mit der `organization_id` einer anderen
  referenzierten Tabelle.
- `organizations` selbst ist keine mandantengebundene Tabelle (sie *ist* der Mandant) und wird
  nicht verlangt; `INSERT INTO <tenant-table>` verlangt stattdessen die Spalte `organization_id`
  in der Spaltenliste.
- Exit 0 = keine Verletzung (auch für Dateien ohne SQL), Exit 1 = Verletzung mit Zeilenangabe.

**Bewusste Grenzen** (analog `validate-job-handler-scope.py`): der Guard liest nur statisch
sichtbare String-Literale. Dynamisch zusammengesetztes SQL (f-Strings, Konkatenation zur
Laufzeit, `getattr`-Indirektion) erkennt er nicht und behauptet das auch nicht. Er ist die zweite
Schicht über der eigentlichen Grenze — dem Prädikat in der Abfrage —, kein Ersatz dafür.

## Red Regression Evidence

*(wird in `IMPLEMENTING` mit dem tatsächlichen Lauf gefüllt)*

## Green Runtime Fix Evidence

*(wird in `IMPLEMENTING` mit dem tatsächlichen Lauf gefüllt)*

## Central Guard Evidence

*(wird in `IMPLEMENTING` mit dem tatsächlichen Lauf gefüllt)*
