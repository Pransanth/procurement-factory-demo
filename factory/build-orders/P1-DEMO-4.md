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

```
python3 -m unittest app.services.test_reporting_org_scope_regression -v
```
```
test_foreign_line_items_do_not_displace_own_items_from_the_top_list ... FAIL
AssertionError: Lists differ: ['B confidential tooling', 'A laptops'] != ['A laptops', 'A chairs']
test_headline_totals_stay_scoped_to_the_requested_organization ... ok
test_top_line_items_contain_no_foreign_organizations_data ... FAIL
AssertionError: Lists differ: ['B confidential tooling', 'A laptops'] != ['A laptops']

Ran 3 tests in 0.004s
FAILED (failures=2)
```
Beide Fehlschläge sind `AssertionError` an der Sicherheits-Assertion selbst: die Position
`B confidential tooling` der fremden Organisation erscheint in `top_line_items` von Org A und
verdrängt bei `top_line_item_limit=2` zusätzlich die eigene Position `A chairs` aus der Liste.
Kein Import-, Namens- oder Syntaxfehler. Der dritte Test (`...headline_totals...`) ist bereits
vor dem Fix grün — er sichert die schon korrekte Kopfzahlen-Abfrage gegen eine Beschädigung
durch die Reparatur ab.

## Green Runtime Fix Evidence

Änderung: `app/services/reporting_service.py:monthly_spend_report()` bindet in der
Line-Item-Abfrage jetzt `WHERE pr.organization_id = ?` mit `organization_id` als erstem
Bind-Parameter und verknüpft den Join tenant-gebunden
(`JOIN suppliers s ON s.id = pr.supplier_id AND s.organization_id = pr.organization_id`). Die
Kopfzahlen-Abfrage ist unverändert.

```
python3 -m unittest app.services.test_reporting_org_scope_regression -v
# 3 tests -> OK (unveränderte Assertionen, jetzt grün)

python3 -m unittest app.services.test_reporting_service app.test_multi_tenant_isolation -v
# 10 tests -> OK

python3 factory/guards/run-app-tests.py
# 72 tests -> OK (69 bestehende + 3 neue Regressionstests)
```

## Central Guard Evidence

Neuer Guard `factory/guards/validate-service-sql-org-scope.py`, eingehängt als vierter Check in
`factory/guards/run-factory-checks.py` (`--services-dir`, Default `app/services`).

```
python3 factory/guards/validate-service-sql-org-scope.py app/services/reporting_service.py
# GÜLTIG: app/services/reporting_service.py (2 SQL-Statement(s) mit organization_id-Praedikat)

python3 factory/guards/validate-service-sql-org-scope.py app/services/procurement_service.py
# ÜBERSPRUNGEN: app/services/procurement_service.py (kein rohes SQL in dieser Datei)

python3 -m unittest factory.guards.test_validate_service_sql_org_scope -v
# 19 tests -> OK, darunter test_unfixed_reporting_query_is_rejected (die Abfrage im Zustand VOR
# dem Fix wird zurückgewiesen) und test_fixed_reporting_query_is_accepted (die Abfrage NACH dem
# Fix wird akzeptiert)

python3 -m unittest factory.guards.test_run_factory_checks -v
# 19 tests -> OK (14 bestehende + 5 neue: scoped/unscoped/ohne-SQL/test_*-ausgenommen/
# Finding-und-Service-Fehler-gemeinsam; diese Datei läuft in GitHub CI, damit die neue Regel
# dort real mitgeprüft wird)

python3 factory/guards/run-factory-checks.py
# Factory-Checks: ALLE BESTANDEN (inkl. [OK] service-sql-guard: reporting_service.py)
```

Ein während der Implementierung aufgetretener, echter Fehlschlag ist hier bewusst dokumentiert:
`.claude/hooks/test_stop_validate_findings.py` baut Wegwerf-Projekte, die nur die vier bisherigen
Guard-Skripte kopieren und **kein** `app/services/`-Verzeichnis haben. Die erste Fassung von
`run_service_sql_checks()` prüfte die Existenz des Guard-Skripts vor der Frage, ob überhaupt
etwas zu prüfen ist, und ließ diesen Test rot laufen. Korrigiert wurde die **Reihenfolge** im
Runner (erst "gibt es Service-Dateien?", dann "gibt es das Guard-Skript?") — ausdrücklich nicht
der Test und ausdrücklich keine Abschwächung: sobald `app/services/` existiert, ist ein fehlendes
Guard-Skript weiterhin ein harter Fehlschlag. Die Hook-Testdatei selbst wurde nicht angefasst
(sie ist schreibgeschützt und liegt außerhalb des Scopes).

```
python3 .claude/hooks/test_stop_validate_findings.py
# 5 tests -> OK (nach der Reihenfolge-Korrektur)

python3 -m unittest factory.guards.test_validate_finding factory.guards.test_validate_job_handler_scope factory.guards.test_validate_review factory.guards.test_create_finding_worktree
# 36 tests -> OK

python3 .claude/hooks/test_subagentstop_write_review.py
# 13 tests -> OK
```

## Nacharbeit aus Review-Runde 1

Die erste unabhängige Review (`finding-closure-reviewer`, Reviewed Commit
`c1ab345a09f0002f38713a86d75c6fd45bcec6ec`) endete mit `Result: PASS`, hielt aber zwei konkrete
Einwände fest. Beide wurden behoben, bevor das Finding weitergeführt wurde — nicht weggeschrieben:

1. **Guard-Dokumentation war breiter als die Implementierung.** Der Guard beanspruchte, Tabellen
   aus `FROM`/`JOIN`/`UPDATE`/`INSERT INTO`/`DELETE FROM` zu erfassen, übersah aber
   komma-separierte `FROM`-Listen (`FROM a x, b y` — nur die erste Tabelle wurde geprüft),
   überging bei `INSERT ... SELECT` die Quelltabellen vollständig und akzeptierte ein
   `INSERT INTO <tenant-table> VALUES (...)` ohne Spaltenliste stillschweigend. Genau diese drei
   Lücken hätten den Befund dieses Findings in leicht anderer Schreibweise erneut durchgelassen.
   Die Implementierung wurde entsprechend erweitert (Komma-Listen, `INSERT ... SELECT`-Quellen,
   fehlende Spaltenliste als Fehler), und die verbleibenden echten Grenzen (Subqueries/CTEs, kein
   Prüfen des *gebundenen Werts*, kein dynamisches SQL) stehen jetzt ausdrücklich im Docstring.
   Sieben neue Testfälle halten das fest: `test_comma_separated_from_list_without_predicates_is_rejected`,
   `test_comma_separated_from_list_scoping_only_the_first_table_is_rejected`,
   `test_fully_scoped_comma_separated_from_list_is_accepted`,
   `test_insert_into_tenant_table_without_column_list_is_rejected`,
   `test_insert_into_non_tenant_table_needs_no_column_list`,
   `test_insert_select_from_unscoped_source_is_rejected`,
   `test_insert_select_from_scoped_source_is_accepted`.
2. **Zählfehler in dieser Datei.** `factory/guards/test_run_factory_checks.py` enthält 14
   bestehende plus 5 neue Fälle, nicht "15 bestehende + 4 neue"; die Gesamtzahl 19 stimmte. Der
   Text oben ist korrigiert. Kein bestehender Fall wurde gelöscht oder abgeschwächt.

Danach erneut ausgeführt:

```
python3 -m unittest factory.guards.test_validate_service_sql_org_scope -v
# 19 tests -> OK (12 aus Runde 1 + 7 neue)

python3 -m unittest factory.guards.test_run_factory_checks -v
# 19 tests -> OK

python3 factory/guards/run-app-tests.py
# 72 tests -> OK

python3 factory/guards/run-factory-checks.py
# Factory-Checks: ALLE BESTANDEN

python3 .claude/hooks/test_stop_validate_findings.py
# 5 tests -> OK
```

Weil sich der Guard-Code dadurch gegenüber dem reviewten Commit geändert hat, wird eine
**zweite, vollständige Review-Runde** gegen den neuen Commit durchgeführt — das Ergebnis von
Runde 1 wird nicht auf den geänderten Stand übertragen.

## Nacharbeit aus Review-Runde 2

Review-Runde 2 (Reviewed Commit `e078606`) endete ebenfalls mit `Result: PASS` und bestätigte,
dass die drei Lücken aus Runde 1 tatsächlich geschlossen sind. Sie fand dabei **eine** verbliebene
Stelle, an der der Guard nach außen aufmacht statt zu:

`INSERT_TARGET_RE` verlangte wörtlich `insert into`, während die Insert-Erkennung in
`check_statement()` jedes mit `insert` beginnende Statement erfasst. Ein
`INSERT OR REPLACE INTO suppliers VALUES (...)` bzw. `INSERT OR IGNORE INTO ...` — in SQLite die
übliche Upsert-Schreibweise — fand damit kein Ziel, enthielt kein `SELECT` und wurde ohne jede
Prüfung akzeptiert. Das ist behoben: beide Regexe akzeptieren jetzt die Konflikt-Klausel
(`or replace|ignore|abort|fail|rollback`), festgehalten durch drei neue Testfälle
(`test_insert_or_replace_without_column_list_is_rejected`,
`test_insert_or_ignore_without_organization_id_column_is_rejected`,
`test_insert_or_replace_with_organization_id_column_is_accepted`).

Die übrigen von Runde 2 genannten Punkte sind **keine** Fehler, sondern echte Grenzen dieses
Guard-Typs; sie stehen deshalb jetzt ausdrücklich in seinem Docstring, statt implizit
wegzufallen: Prädikate werden gegen das gesamte Literal gematcht (bei mehreren Statements in einem
`executescript`-Literal bzw. unter `OR`/`NOT` zählt ein Prädikat als vorhanden), die rechte Seite
`<other>.organization_id` wird nicht gegen die tatsächlich referenzierten Tabellen geprüft, und
`REPLACE INTO ...` (ohne `INSERT`) landet im Lesepfad und schlägt dort eher zu viel als zu wenig
Alarm. Ebenfalls unverändert und bewusst: der Guard prüft die *Anwesenheit* eines Prädikats, nie
den gebundenen Wert — die eigentliche Grenze bleibt die Abfrage selbst.

```
python3 -m unittest factory.guards.test_validate_service_sql_org_scope -v
# 22 tests -> OK (19 aus Runde 2 + 3 neue)

python3 factory/guards/run-app-tests.py
# 72 tests -> OK

python3 factory/guards/run-factory-checks.py
# Factory-Checks: ALLE BESTANDEN
```

Auch dieser Stand wird erneut unabhängig reviewt (Runde 3), weil sich der Guard-Code seit Runde 2
wieder geändert hat.
