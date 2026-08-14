# Bauauftrag: P1-DEMO-5

Bezug: [`factory/findings/P1-DEMO-5.md`](../findings/P1-DEMO-5.md) (Status: `ANALYZED`)

Dieser Bauauftrag legt fest, **was** in der nächsten Phase (`IMPLEMENTING`) gebaut werden darf,
in welcher Reihenfolge, und woran Erfolg gemessen wird.

## Primäre Sicherheitsgrenze

Die primäre Sicherheitsgrenze ist die Autorisierungsprüfung in
`app/services/user_admin_service.py:change_user_role()` selbst — und zwar in ihrer **positiven**
Form:

```python
ROLE_ADMINISTERING_ROLES = ("admin",)
...
if actor.role not in ROLE_ADMINISTERING_ROLES:
    raise ValueError(...)
```

Sie steht an genau der Stelle der bisherigen Ausschlussprüfung: nachdem der Akteur aufgelöst ist,
vor dem Laden des Ziels und vor jedem Schreibzugriff. Damit administriert nur noch `admin` Rollen;
`approver` verliert eine Autorität, die er nie haben sollte.

**Bewusst nicht Teil dieses Bauauftrags: ein Verbot der Änderung der eigenen Rolle.** Mit einer
Allowlist auf `admin` ist Selbst-Eskalation bereits unmöglich (ein `admin` ist bereits maximal
privilegiert, eine Änderung der eigenen Rolle kann nur eine Herabstufung sein). Ein pauschales
Selbstverbot würde den einzigen Weg entfernen, auf dem ein `admin` die eigenen Rechte reduzieren
kann. Das ist der Unterschied zu P1-DEMO-3, wo die Entscheidung über die *eigene Anfrage*
unabhängig von der Rolle ein Integritätsproblem ist.

Die **zusätzliche**, dauerhafte Schranke ist der neue AST-Guard
`factory/guards/validate-service-role-authorization.py` (siehe "Central Guard"). Er ist nicht die
Sicherheitsgrenze, sondern macht die *Form* des Fehlers in der Service-Schicht unschreibbar.

## Verbindliche Reihenfolge

1. **Regressionstest zuerst, gegen den heutigen Code**, gemäß Regression Test Plan des Findings.
2. **Die Tests müssen aus dem fachlich richtigen Grund rot sein**: `change_user_role` gibt heute
   klaglos einen `User` mit `role == "admin"` zurück, statt `ValueError` zu werfen — kein Import-,
   Namens- oder Syntaxfehler.
3. **Erst danach**: Ersetzen der Ausschlussprüfung durch die Allowlist-Prüfung.
4. **Erst danach**: Bestätigen, dass die Regressionstests grün sind, ohne Abschwächung, und dass
   `app/services/test_user_admin_service.py` unverändert grün bleibt.
5. **Erst danach**: den zentralen Guard bauen, samt eigener Tests, und in den kanonischen Runner
   einhängen.

## Acceptance Criteria

1. Die neuen Regressionstests sind gegen den heutigen Code nachweislich rot, aus dem fachlich
   richtigen Grund (Fälle 1–3 des Regression Test Plans).
2. Dieselben Regressionstests sind nach dem Fix grün, mit unveränderten Kernassertionen.
3. Der Positivfall (ein `admin` befördert ein `member`) bleibt vor und nach dem Fix grün — die
   Reparatur darf nicht einfach alles verbieten.
4. `app/services/test_user_admin_service.py` bleibt unverändert grün.
5. `app/test_multi_tenant_isolation.py` und `app/repositories/test_users.py` bleiben grün.
6. Der neue Guard weist die **unreparierte** Prüfzeile zurück und akzeptiert die reparierte —
   beides als Fixture in seinen eigenen Tests festgehalten.
7. Alle App-Tests sind grün (`python3 factory/guards/run-app-tests.py`).
8. Alle Factory-Guard-Tests sind grün, inklusive der erweiterten
   `factory.guards.test_run_factory_checks`.
9. `python3 factory/guards/run-factory-checks.py` beendet sich mit Exit-Code 0.

## Scope

**Erlaubt:**
- Änderung ausschließlich an der Autorisierungsprüfung in `app/services/user_admin_service.py`
  (neue Modulkonstante + `not in`-Prüfung anstelle der `== "member"`-Prüfung).
- Neue Testdatei `app/services/test_user_admin_role_escalation_regression.py`.
- Neuer Guard `factory/guards/validate-service-role-authorization.py` und dessen Testdatei
  `factory/guards/test_validate_service_role_authorization.py`.
- Einhängen des Guards in `factory/guards/run-factory-checks.py` (fünfter Check über das bereits
  vorhandene `--services-dir`) und entsprechende Ergänzung von
  `factory/guards/test_run_factory_checks.py`.

**Nicht erlaubt / außerhalb dieses Bauauftrags:**
- Keine Änderung an `app/repositories/users.py` — `update_role` ist die Speicherschicht, nicht die
  Entscheidungsstelle; ihre Org-Prüfung ist intakt.
- Keine Änderung an `app/db.py` (die `role`-CHECK-Constraint ist korrekt).
- Keine Änderung an `app/repositories/approvals.py` (P1-DEMO-3, bereits korrekt in
  Allowlist-Form) und keine an `app/services/reporting_service.py` (P1-DEMO-4, abgeschlossen).
- Keine Änderung an bestehenden Tests.
- Keine Änderung an `.github/workflows/factory-ci.yml`, `factory/README.md`, `CLAUDE.md` oder an
  Permissions/Sandbox/Hooks — außerhalb des Schreib-Scopes dieses Laufs. Der neue Guard erreicht
  CI ohne Workflow-Änderung über `run-factory-checks.py` und über
  `factory.guards.test_run_factory_checks`.

## Central Guard

`factory/guards/validate-service-role-authorization.py`, deterministisch, ohne KI, ohne Netzwerk:

- Prüft eine einzelne `.py`-Datei aus der Service-Schicht.
- Meldet per AST jede `Compare`-Node mit `==` oder `!=`, bei der eine Seite ein Rollenwert
  (Attributzugriff `.role` oder ein Name `role`/`actor_role`/`user_role`) und die andere ein
  String-Literal ist.
- Erlaubt und erwartet stattdessen die Mitgliedschaftsprüfung `in` / `not in` gegen eine explizite
  Allowlist (Modulkonstante oder Literal-Tupel/-Menge).
- Exit 0 = keine Verletzung (auch für Dateien ohne Rollenlogik), Exit 1 = Verletzung mit
  Zeilenangabe und Nennung der gefundenen Form.

**Bewusste Grenzen** (analog den bestehenden Guards): der Guard erkennt die *syntaktische Form*
einer Autorisierungsentscheidung, nicht ihre Semantik. Er kann nicht prüfen, ob die Allowlist die
*richtigen* Rollen enthält, ob sie zur Laufzeit umdefiniert wird, oder ob eine Prüfung überhaupt
stattfindet — eine Funktion ganz ohne Rollenprüfung ist für ihn unauffällig. Er ist die zweite
Schicht über der eigentlichen Grenze (der Prüfung in der Funktion), kein Ersatz dafür.

## Red Regression Evidence

```
python3 -m unittest app.services.test_user_admin_role_escalation_regression -v
```
```
test_admin_can_still_promote_a_member ... ok
test_approver_cannot_promote_a_colleague ... FAIL
AssertionError: ValueError not raised
test_approver_cannot_promote_themselves_to_admin ... FAIL
AssertionError: ValueError not raised
test_rejected_escalation_writes_no_audit_log_entry ... FAIL
AssertionError: ValueError not raised

Ran 4 tests in 0.003s
FAILED (failures=3)
```
Alle drei Fehlschläge sind `AssertionError: ValueError not raised` an der Sicherheits-Assertion
selbst: `change_user_role()` gibt für einen `approver`-Akteur klaglos einen aktualisierten `User`
zurück, statt abzulehnen — sowohl bei der Beförderung der eigenen Person als auch bei der eines
Kollegen, und der Vorgang landet zusätzlich im Audit-Log. Kein Import-, Namens- oder Syntaxfehler.
Der vierte Test (`test_admin_can_still_promote_a_member`) ist bereits vor dem Fix grün — er
verhindert eine "Reparatur", die einfach alles verbietet.

## Green Runtime Fix Evidence

Änderung: `app/services/user_admin_service.py` erhält die Modulkonstante
`ROLE_ADMINISTERING_ROLES = ("admin",)`; die Prüfung `if actor.role == "member"` wird zu
`if actor.role not in ROLE_ADMINISTERING_ROLES`, an derselben Stelle (nach dem Auflösen des
Akteurs, vor dem Laden des Ziels, vor jedem Schreibzugriff). Fehlermeldung und Signatur bleiben
unverändert; kein Selbstverbot, siehe Begründung unter "Primäre Sicherheitsgrenze".

```
python3 -m unittest app.services.test_user_admin_role_escalation_regression -v
# 4 tests -> OK (unveränderte Assertionen, jetzt grün)

python3 -m unittest app.services.test_user_admin_service app.repositories.test_users app.test_multi_tenant_isolation -v
# 19 tests -> OK (keine bestehende Testdatei angefasst)

python3 factory/guards/run-app-tests.py
# 76 tests -> OK (72 bestehende + 4 neue Regressionstests)
```

## Central Guard Evidence

Neuer Guard `factory/guards/validate-service-role-authorization.py`, eingehängt als fünfter Check
in `factory/guards/run-factory-checks.py` über das bereits vorhandene `--services-dir`.

```
python3 factory/guards/validate-service-role-authorization.py app/services/user_admin_service.py
# GÜLTIG: app/services/user_admin_service.py (keine Rollenpruefung per Gleichheitsvergleich)

python3 -m unittest factory.guards.test_validate_service_role_authorization -v
# 10 tests -> OK, darunter test_unfixed_exclusion_check_is_rejected (die Prüfzeile im Zustand VOR
# dem Fix wird zurückgewiesen), test_fixed_allowlist_check_is_accepted (die Zeile NACH dem Fix
# wird akzeptiert), test_inequality_against_a_single_role_is_rejected (auch die invertierte Form
# "!= 'admin'" ist eine Einzelrollen-Entscheidung) und
# test_role_mentioned_only_inside_a_message_is_accepted (ein Rollenwert in einer Fehlermeldung ist
# kein Vergleich und darf nicht anschlagen -- genau das tut das reparierte Modul)

python3 -m unittest factory.guards.test_run_factory_checks -v
# 23 tests -> OK (19 bestehende + 4 neue: Allowlist-Form, Ausschluss-Form, Datei ohne Rollenlogik,
# und beide Service-Guards melden unabhängig voneinander ihre eigene Verletzung; diese Datei läuft
# in GitHub CI, damit die neue Regel dort real mitgeprüft wird)

python3 factory/guards/run-factory-checks.py
# Factory-Checks: ALLE BESTANDEN, inkl.
#   [OK] service-role-guard: procurement_service.py
#   [OK] service-role-guard: reporting_service.py
#   [OK] service-role-guard: user_admin_service.py

python3 -m unittest factory.guards.test_validate_finding factory.guards.test_validate_job_handler_scope factory.guards.test_validate_review factory.guards.test_create_finding_worktree factory.guards.test_validate_service_sql_org_scope factory.guards.test_validate_service_role_authorization
# 68 tests -> OK

python3 .claude/hooks/test_stop_validate_findings.py
# 5 tests -> OK
```
