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

*(wird in `IMPLEMENTING` mit dem tatsächlichen Lauf gefüllt)*

## Green Runtime Fix Evidence

*(wird in `IMPLEMENTING` mit dem tatsächlichen Lauf gefüllt)*

## Central Guard Evidence

*(wird in `IMPLEMENTING` mit dem tatsächlichen Lauf gefüllt)*
