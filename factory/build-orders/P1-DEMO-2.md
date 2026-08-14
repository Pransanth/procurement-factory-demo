# Bauauftrag: P1-DEMO-2

Bezug: [`factory/findings/P1-DEMO-2.md`](../findings/P1-DEMO-2.md) (Status: `ANALYZED`)

Dieser Bauauftrag legt fest, **was** in der nächsten Phase (`IMPLEMENTING`) gebaut werden darf,
in welcher Reihenfolge, und woran Erfolg gemessen wird.

## Primäre Sicherheitsgrenze

Die primäre Sicherheitsgrenze ist eine explizite Cross-Organisation-Prüfung in
`app/repositories/procurement_requests.py:create()`: bevor die Zeile eingefügt wird, muss
`suppliers.get_by_id(conn, organization_id, supplier_id)` aufgerufen werden; liefert dieser
Aufruf `None` (der Supplier existiert nicht oder gehört zu einer anderen Organisation), wird
`ValueError` geworfen und keine Zeile eingefügt. Das ist derselbe Musterschutz, den
`app/repositories/approvals.py:record_decision` bereits für `procurement_request_id` und
`approver_user_id` verwendet.

## Verbindliche Reihenfolge

1. **Regressionstest zuerst, gegen den heutigen Code.** Ein Test muss beweisen, dass
   `procurement_requests.create()` heute anstandslos eine Zeile mit organisationsfremdem
   `supplier_id` anlegt (siehe Reproduktion in `factory/findings/P1-DEMO-2.md`).
2. **Der Test muss aus dem fachlich richtigen Grund rot sein**: die Assertion erwartet, dass
   `create()` mit einem `supplier_id` einer fremden Organisation `ValueError` wirft; heute wirft
   sie nichts, sondern legt die Zeile klaglos an.
3. **Erst danach**: Implementierung der Prüfung in `create()`.
4. **Erst danach**: Bestätigen, dass derselbe Regressionstest jetzt grün ist, ohne die
   Kernassertion abzuschwächen.

## Acceptance Criteria

1. Regressionstest ist gegen den heutigen Code nachweislich rot, aus dem fachlich richtigen
   Grund.
2. Derselbe Regressionstest ist nach dem Fix grün, mit unveränderter Kernassertion.
3. `app/repositories/test_procurement_requests.py` und `app/services/test_procurement_service.py`
   bleiben grün (kein legitimer Aufrufer verwendet heute einen organisationsfremden
   `supplier_id`).
4. `app/test_multi_tenant_isolation.py` bleibt grün.
5. Alle App-Tests sind grün (`python3 factory/guards/run-app-tests.py`).
6. `python3 factory/guards/run-factory-checks.py` beendet sich mit Exit-Code 0.

## Scope

**Erlaubt:**
- Änderung ausschließlich in `app/repositories/procurement_requests.py` (neuer Import von
  `app.repositories.suppliers`, neue Validierung in `create()`).
- Eine neue Testdatei unter `app/repositories/`, die genau diesen Regressionsfall testet.

**Nicht erlaubt / außerhalb dieses Bauauftrags:**
- Keine Änderung am Datenbankschema (`app/db.py`).
- Keine Änderung an `app/repositories/approvals.py`, `app/jobs/*` oder anderen Repositories.
- Keine Prüfung von `requested_by_user_id` (separates, hier nicht bestätigtes Thema).
- Kein neues Guard-Skript unter `factory/guards/` -- die Central-Guard-Wirkung entsteht hier
  durch Aufnahme des Regressionstests in die bereits zentrale, automatisch entdeckte
  `run-app-tests.py`-Suite (siehe Central Guard Plan im Finding), nicht durch einen neuen
  AST-Guard.

## Red Regression Evidence

```
python3 -m unittest app.repositories.test_supplier_org_scope_regression -v
```
```
test_create_rejects_supplier_from_another_organization ... FAIL
AssertionError: ValueError not raised

Ran 1 test in 0.002s
FAILED (failures=1)
```
Fehlschlag ist ein `AssertionError` an der Sicherheits-Assertion selbst (`create()` warf trotz
organisationsfremdem `supplier_id` keinen Fehler), keine Exception durch fehlenden Import oder
Syntaxfehler.

## Green Runtime Fix Evidence

Änderung: `app/repositories/procurement_requests.py` importiert jetzt `app.repositories.suppliers`
und `create()` ruft vor dem INSERT `suppliers.get_by_id(conn, organization_id, supplier_id)` auf;
liefert das `None`, wirft `create()` `ValueError` und legt keine Zeile an.

```
python3 -m unittest app.repositories.test_supplier_org_scope_regression -v
# 1 test -> OK (unveränderte Assertion, jetzt grün)

python3 -m unittest app.repositories.test_procurement_requests app.services.test_procurement_service app.test_multi_tenant_isolation -v
# 15 tests -> OK

python3 factory/guards/run-app-tests.py
# 55 tests -> OK (54 bestehende + 1 neuer Regressionstest)

python3 factory/guards/run-factory-checks.py
# Factory-Checks: ALLE BESTANDEN
```
