# Bauauftrag: P1-DEMO-3

Bezug: [`factory/findings/P1-DEMO-3.md`](../findings/P1-DEMO-3.md) (Status: `ANALYZED`)

Dieser Bauauftrag legt fest, **was** in der nächsten Phase (`IMPLEMENTING`) gebaut werden darf,
in welcher Reihenfolge, und woran Erfolg gemessen wird.

## Primäre Sicherheitsgrenze

Die primäre Sicherheitsgrenze sind zwei zusätzliche Prüfungen in
`app/repositories/approvals.py:record_decision()`, nach den bestehenden
Organisationszugehörigkeits-Prüfungen und vor dem `INSERT`:

1. **Rollenprüfung**: der Approver (bereits über `users.get_by_id` geladen) muss die Rolle
   `approver` oder `admin` haben; sonst `ValueError`.
2. **Self-Approval-Prüfung**: `approver_user_id` darf nicht gleich der `requested_by_user_id`
   des zu entscheidenden Requests sein; sonst `ValueError`. Diese Prüfung gilt unabhängig von der
   Rolle -- auch ein `admin` darf nicht über die eigene Anfrage entscheiden.

## Verbindliche Reihenfolge

1. **Regressionstest zuerst, gegen den heutigen Code.** Zwei Fälle müssen bewiesen werden: (a)
   ein Nutzer mit Rolle `member` kann heute anstandslos eine Anfrage genehmigen; (b) der
   Ersteller einer Anfrage kann heute anstandslos über die eigene Anfrage entscheiden (siehe
   Reproduktion in `factory/findings/P1-DEMO-3.md`).
2. **Der Test muss aus dem fachlich richtigen Grund rot sein**: die Assertion erwartet
   `ValueError`; heute liefert `record_decision()` stattdessen klaglos ein `Approval`-Objekt mit
   `decision == "approved"`.
3. **Erst danach**: Implementierung beider Prüfungen in `record_decision()`.
4. **Erst danach**: Bestätigen, dass beide Regressionstests jetzt grün sind, ohne die
   Kernassertionen abzuschwächen.

## Acceptance Criteria

1. Beide Regressionstests sind gegen den heutigen Code nachweislich rot, aus dem fachlich
   richtigen Grund.
2. Dieselben Regressionstests sind nach dem Fix grün, mit unveränderten Kernassertionen.
3. `app/repositories/test_approvals.py` und `app/services/test_procurement_service.py` bleiben
   grün (kein bestehender Test verwendet heute einen `member`-Approver oder Self-Approval).
4. `app/test_multi_tenant_isolation.py` bleibt grün.
5. Alle App-Tests sind grün (`python3 factory/guards/run-app-tests.py`).
6. `python3 factory/guards/run-factory-checks.py` beendet sich mit Exit-Code 0.

## Scope

**Erlaubt:**
- Änderung ausschließlich in `app/repositories/approvals.py` (zwei neue Prüfungen in
  `record_decision()`, kein neuer Import nötig -- `role` und `requested_by_user_id` sind bereits
  über die vorhandenen `approver`- und `request`-Objekte verfügbar).
- Eine neue Testdatei unter `app/repositories/`, die genau diese beiden Regressionsfälle testet.

**Nicht erlaubt / außerhalb dieses Bauauftrags:**
- Keine Änderung am Datenbankschema (`app/db.py`) -- die `role`-CHECK-Constraint existiert
  bereits korrekt.
- Keine Änderung an `app/repositories/procurement_requests.py` (bereits unabhängig durch
  P1-DEMO-2 behoben, kein Overlap).
- Keine Änderung an `app/jobs/*` oder anderen Repositories.
- Kein neues Guard-Skript unter `factory/guards/` -- die Central-Guard-Wirkung entsteht hier
  durch Aufnahme der Regressionstests in die bereits zentrale, automatisch entdeckte
  `run-app-tests.py`-Suite (siehe Central Guard Plan im Finding), nicht durch einen neuen
  AST-Guard.

## Red Regression Evidence

```
python3 -m unittest app.repositories.test_approval_role_scope_regression -v
```
```
test_member_role_cannot_approve_a_request ... FAIL
AssertionError: ValueError not raised
test_requester_cannot_approve_their_own_request ... FAIL
AssertionError: ValueError not raised

Ran 2 tests in 0.003s
FAILED (failures=2)
```
Beide Fehlschläge sind `AssertionError` an der Sicherheits-Assertion selbst (`record_decision()`
warf trotz unauthorisiertem bzw. selbstgenehmigtem Approver keinen Fehler), keine Exception durch
fehlenden Import oder Syntaxfehler.

## Green Runtime Fix Evidence

Änderung: `app/repositories/approvals.py:record_decision()` prüft nach den bestehenden
Organisationszugehörigkeits-Checks jetzt zusätzlich `approver.role in ("approver", "admin")` und
`approver_user_id != request.requested_by_user_id`, jeweils mit `ValueError` bei Verstoß, vor dem
`INSERT`. Kein neuer Import nötig -- `role` und `requested_by_user_id` sind bereits über die
vorhandenen `approver`- und `request`-Objekte verfügbar.

```
python3 -m unittest app.repositories.test_approval_role_scope_regression -v
# 2 tests -> OK (unveränderte Assertionen, jetzt grün)

python3 -m unittest app.repositories.test_approvals app.services.test_procurement_service app.test_multi_tenant_isolation -v
# 15 tests -> OK

python3 factory/guards/run-app-tests.py
# 57 tests -> OK (55 bestehende + 2 neue Regressionstests)

python3 factory/guards/run-factory-checks.py
# Factory-Checks: ALLE BESTANDEN
```
