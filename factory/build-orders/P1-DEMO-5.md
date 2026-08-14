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

## Nacharbeit aus Review-Runde 1

Review-Runde 1 (`finding-closure-reviewer`, Reviewed Commit
`0df18bc154e6adc44ecf86d1e76cb686fbf3361b`) endete mit `Result: PASS` und ohne blockierende
Einwände; der Reviewer bestätigte durch eigenes Nachverfolgen der AST-Logik, dass der Guard alle
vier Formen (Normalform, vertauschte Operanden, einfache Variable, `!=`) erkennt und die
Allowlist-Form durchlässt, und stimmte der bewussten Auslassung eines Selbstverbots ausdrücklich
zu. Drei nicht blockierende Punkte wurden trotzdem vor dem Abschluss erledigt, statt sie als
"Risiko" stehenzulassen:

1. **Überzeichnete Formulierung im Finding.** Der Central Guard Plan sagte, der Guard mache die
   Ausschluss-Form "unschreibbar" in der Service-Schicht. Tatsächlich matcht er *Vergleiche gegen
   String-Literale*; zwei Umschreibungen derselben Entscheidung kommen durch — ein Vergleich gegen
   eine benannte Konstante (`actor.role == MEMBER_ROLE`) und ein Ausschluss als
   Mitgliedschaftstest über eine Denylist (`if actor.role in DENIED_ROLES`). Der Satz ist
   korrigiert, beide Lücken stehen jetzt ausdrücklich im Guard-Docstring und sind als
   Known-Limitation-Fixtures festgehalten
   (`test_known_limitation_comparison_against_named_constant_is_not_detected`,
   `test_known_limitation_denylist_membership_is_not_detected`) — eine dokumentierte Lücke statt
   einer stillschweigend angenommenen Abwesenheit.
2. **`assertRaises` → `assertRaisesRegex`.** Die drei Ablehnungsfälle prüften nur den Ausnahmetyp.
   `change_user_role` kann `ValueError` auch aus drei anderen Gründen werfen (unzulässiger
   Rollenwert, Akteur oder Ziel nicht in der Organisation), sodass ein späteres Entfernen der
   Autorisierungsprüfung selbst unbemerkt bleiben könnte. Die Tests pinnen jetzt die Meldung
   `not authorized to administer user roles`. Das ist eine **Verschärfung** der Assertionen, keine
   Abschwächung.
3. **Bewusste Auslassung war durch nichts festgehalten.** Ein neuer Test
   (`test_admin_may_still_demote_themselves`) sichert die dokumentierte Entscheidung ab, dass ein
   `admin` die eigene Rolle weiterhin herabstufen darf — damit kann sie nicht stillschweigend
   umgedreht werden.

Nicht geändert (bewusst, mit Begründung): `app/repositories/users.py:update_role` bleibt
unauthentifiziert — sie ist die Speicherschicht, die Entscheidung liegt in der Service-Funktion
(außerhalb des Scopes dieses Bauauftrags). Der Guard bleibt auf `app/services/` beschränkt; die
gleichartige Entscheidung in `app/repositories/approvals.py` liegt außerhalb dieses Findings und
ist dort bereits in der korrekten Allowlist-Form geschrieben.

```
python3 -m unittest app.services.test_user_admin_role_escalation_regression -v
# 5 tests -> OK (4 aus Runde 1 + 1 neuer Selbst-Herabstufungs-Test, verschärfte Assertionen)

python3 -m unittest factory.guards.test_validate_service_role_authorization -v
# 12 tests -> OK (10 aus Runde 1 + 2 Known-Limitation-Fixtures)

python3 factory/guards/run-app-tests.py
# 77 tests -> OK

python3 factory/guards/run-factory-checks.py
# Factory-Checks: ALLE BESTANDEN
```

Weil sich Guard-Docstring und Tests gegenüber dem reviewten Commit geändert haben, wird eine
**zweite, vollständige Review-Runde** gegen den neuen Commit durchgeführt.

## Nacharbeit aus Review-Runde 2 (Ergebnis: FAIL)

Review-Runde 2 (Reviewed Commit `36b2362`) endete mit **`Result: FAIL`** — zu Recht, und der
Fehlschlag steht hier bewusst im Protokoll, statt weggeschrieben zu werden.

**Der Befund des Reviewers:** Im Feld `Verification Evidence` des Findings stand, als Teil eines
ausdrücklich als "Am 2026-08-14 ... frisch ausgefuehrt" beschriebenen Laufs, die Zahl
"die sechs Guard-Testmodule zusammen -- 68 Tests OK". Diese Zahl stammte aus Runde 1 und wurde bei
der Nacharbeit nicht neu gemessen: durch die zwei neuen Known-Limitation-Fixtures hat
`test_validate_service_role_authorization` seither 12 statt 10 Fälle — dieselbe Satzhälfte des
Feldes sagte das sogar korrekt. Der Wert widersprach sich also innerhalb eines Satzes und war eine
fortgeschriebene statt einer gemessenen Angabe, ausgerechnet in dem Feld, das konkret benennen
soll, welche Tests tatsächlich grün liefen.

**Reaktion:** die sechs Module wurden neu ausgeführt und der reale Wert eingetragen — kein
Nachrechnen, kein Schätzen:

```
python3 -m unittest factory.guards.test_validate_finding factory.guards.test_validate_job_handler_scope factory.guards.test_validate_review factory.guards.test_create_finding_worktree factory.guards.test_validate_service_sql_org_scope factory.guards.test_validate_service_role_authorization
# Ran 70 tests -> OK   (14 + 7 + 9 + 6 + 22 + 12)
```

Zur Kontrolle wurden bei derselben Gelegenheit auch die übrigen im Feld genannten Zahlen neu
gemessen; sie stimmten unverändert:

```
python3 -m unittest factory.guards.test_run_factory_checks
# Ran 23 tests -> OK

python3 -m unittest app.services.test_user_admin_service app.repositories.test_users app.test_multi_tenant_isolation
# Ran 19 tests -> OK

python3 .claude/hooks/test_subagentstop_write_review.py
# Ran 13 tests -> OK
```

Die beiden weiteren Punkte des Reviewers waren zum Zeitpunkt seiner Lektüre noch offen und sind
Teil des regulären Ablaufs: `CI Evidence` nennt inzwischen zusätzlich den grünen Lauf für den
reviewten Commit `36b2362` (Actions-Run `31811982062`), und das Feld `Review Artifact` wird — wie
im Workflow vorgesehen — erst mit dem Closure-Commit gesetzt, nachdem eine Review-Runde mit
`PASS` vorliegt.

Es folgt eine **dritte, vollständige Review-Runde**. Der `FAIL` aus Runde 2 wird nicht
überschrieben oder umgedeutet: er bleibt als Grund dokumentiert, warum es diese Runde gibt.

## Abschluss: Review-Runde 3

Runde 3 (Reviewed Commit `7e6dfde`, Reviewer Agent ID `a75ffdcef8be2d131`) endete mit
`Result: PASS` und **ohne Einwände**. Der Reviewer hat die beanstandete Zahl nicht übernommen,
sondern selbst nachgezählt (14 + 7 + 9 + 6 + 22 + 12 = 70) und zusätzlich geprüft, dass die alte
68 für den damaligen Stand rechnerisch korrekt war — der Verlauf ist damit konsistent, nicht
nachträglich geglättet. Ebenso hat er jede weitere Zahl im Feld `Verification Evidence` aus dem
Dateiinhalt reproduziert (23, 19, 77 = 72 + 5, 5, 13, 12) und bestätigt, dass kein bestehender
Test entfernt, umbenannt oder abgeschwächt wurde.

Das Artefakt unter `factory/reviews/P1-DEMO-5.md` stammt ausschließlich aus dem
SubagentStop-Hook und wurde bei jeder Runde von ihm überschrieben; es trägt jetzt die Provenienz
von Runde 3 (`PASS`). Der `FAIL` aus Runde 2 bleibt in diesem Bauauftrag dokumentiert, damit das
Überschreiben des Artefakts den Verlauf nicht verwischt.

Die von Runde 3 genannten Restrisiken sind bewusste, dokumentierte Grenzen und begründen keine
weitere Runde:

- `app/repositories/users.py:update_role` bleibt unauthentifiziert (Speicherschicht; die
  Entscheidung liegt in der Service-Funktion) — außerhalb des Scopes dieses Bauauftrags.
- Der Guard sieht nur `app/services/` und nur die Literal-Vergleichsform; beide Grenzen stehen im
  Docstring und sind als Fixtures festgehalten.
- `.github/workflows/factory-ci.yml` führt die Guard-Unit-Tests der beiden neuen Guards nicht
  einzeln auf; in CI wirken sie über den kanonischen Runner und über
  `factory.guards.test_run_factory_checks`. Eine Workflow-Änderung war ausdrücklich außerhalb des
  Schreib-Scopes dieses Laufs.
- Dass ein `admin` sich selbst herabstufen darf, ist die bewusst getroffene Entscheidung dieses
  Bauauftrags und jetzt durch einen Test festgehalten.

Damit sind alle Acceptance Criteria erfüllt; das Finding geht auf `READY_FOR_CLOSURE` und
anschließend auf `CLOSED`, beides von `validate-finding.py` und dem kanonischen Runner bestätigt.
