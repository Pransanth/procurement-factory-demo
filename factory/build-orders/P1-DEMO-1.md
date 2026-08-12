# Bauauftrag: P1-DEMO-1

Bezug: [`factory/findings/P1-DEMO-1.md`](../findings/P1-DEMO-1.md) (Status: `ANALYZED`)

Dieser Bauauftrag legt fest, **was** in der nächsten Phase (`IMPLEMENTING`) gebaut werden darf,
**in welcher Reihenfolge**, und **woran Erfolg gemessen wird**. Er ist selbst kein Code und
enthält keinen. Solange dieser Bauauftrag nicht in eine `IMPLEMENTING`-Phase überführt wurde,
wird nichts aus ihm umgesetzt.

## Primäre Sicherheitsgrenze

Die primäre, technisch erzwungene Sicherheitsgrenze für Background Jobs ist ein
**`ScopedRepositories`-Objekt**, das zur Laufzeit an genau eine `organization_id` gebunden ist:

- Es wird **ausschließlich** vom Job-Runner (`app/jobs/queue.py:run_pending`) beim Start eines
  einzelnen Jobs aus `payload["organization_id"]` konstruiert — an keiner anderen Stelle im
  System.
- Job-Handler erhalten künftig dieses gebundene Objekt anstelle der rohen `sqlite3.Connection`.
  Ihr Zugriff auf org-gescopte Repository-Funktionen läuft ausschließlich über dieses Objekt.
- Das API des `ScopedRepositories`-Objekts darf **keine** Methode besitzen, die eine
  `organization_id` als Argument entgegennimmt. Die Organisation ist beim Erzeugen des Objekts
  bereits endgültig festgelegt — nicht durch jeden einzelnen Aufruf neu wählbar.
- Konsequenz: Ein Job-Handler kann im vorgesehenen API **keine beliebige fremde
  `organization_id`** mehr an einen tenant-gebundenen Repository-Aufruf übergeben, weil es dafür
  keinen Parameter mehr gibt, den er falsch befüllen könnte. Das ist der Unterschied zwischen
  "die Regel beachten müssen" und "die falsche Verwendung ist technisch nicht darstellbar".

Der `ScopedRepositories`-Wrapper muss ein **dünner** Wrapper (z. B. partielle Bindung) um die
bestehenden Repository-Funktionen in `app/repositories/*.py` sein — keine Duplikation von
Abfragelogik. Die bestehenden, ungebundenen Repository-Funktionen bleiben für den interaktiven
Pfad (`app/services/procurement_service.py`) unverändert erhalten; dieser Pfad ist nicht
Gegenstand dieses Bauauftrags.

## Rolle des AST-Guards

Der spätere AST-basierte Guard (nach Vorbild von `factory/guards/validate-finding.py`) ist eine
**zusätzliche Factory-Schranke**, die verhindern soll, dass ein zukünftiger Handler das
`ScopedRepositories`-Objekt umgeht (z. B. durch direkten Import von `app.repositories.*` oder
Annahme eines rohen `conn`-/`organization_id`-Parameters). Er ist ausdrücklich **nicht** die
primäre Sicherheitsgrenze — er ist ein statischer Zweitcheck, der eine Umgehung der eigentlichen
Laufzeitgrenze erkennen soll, falls sie doch versucht wird. Die primäre Sicherheitsgrenze ist und
bleibt die Struktur des `ScopedRepositories`-API selbst.

## Verbindliche Reihenfolge

Diese Reihenfolge ist nicht optional. Jeder Schritt setzt den vorherigen voraus:

1. **Regressionstest zuerst, gegen den heutigen Code.** Bevor irgendein Produktionscode
   geändert wird, muss ein Test entstehen, der mit dem **heutigen** `(conn, payload)`-API
   (`app/jobs/queue.py`, `app/jobs/handlers.py` unverändert) tatsächlich beweist: ein
   fehlerhaft geschriebener Handler, der für einen Job der Organisation A eingeplant ist, kann
   eine lesende oder schreibende Operation gegen Daten der Organisation B durchführen, wenn er
   (aus Versehen, wie ein zukünftiger Entwickler es tun könnte) die falsche `organization_id`
   verwendet.
2. **Der Test muss aus dem fachlich richtigen Grund rot sein.** "Rot" heißt hier konkret: der
   Test formuliert die Erwartung *"ein Job für Organisation A darf Organisation B niemals
   berühren"* und schlägt fehl, **weil genau das nicht zutrifft** — nicht wegen eines Tippfehlers,
   eines fehlenden Imports oder einer unabhängigen Fehlerursache. Vor der Umsetzung ist explizit
   zu verifizieren, dass der Fehlschlag aus diesem Grund erfolgt (z. B. durch eine Assertion, die
   direkt die betroffenen Zeilen/Werte der Organisation B prüft).
3. **Erst danach**: Implementierung der Laufzeit-Sicherheitsgrenze (`ScopedRepositories`,
   Anpassung von `app/jobs/queue.py` und `app/jobs/handlers.py`).
4. **Erst danach**: Migration der beiden bestehenden Handler (`app/jobs/approval_reminder.py`,
   `app/jobs/audit_log_archival.py`) auf das neue `(scope, payload)`-API.
5. **Erst danach**: Bau des AST-Guards als zusätzliche Factory-Schranke.

Der Regressionstest aus Schritt 1 bleibt danach im Test-Suite erhalten und muss nach Schritt 4
grün sein — mit derselben Assertion, nicht mit einer abgeschwächten.

## Acceptance Criteria

Die Umsetzung gilt erst als abgeschlossen, wenn **alle** Punkte erfüllt sind:

1. Der Regressionstest aus Schritt 1 ist gegen den heutigen Code (vor jeder Produktionsänderung
   aus diesem Bauauftrag) nachweislich rot, aus dem fachlich richtigen Grund (siehe oben).
2. Derselbe Regressionstest ist nach Abschluss von Schritt 3 und 4 grün — ohne dass seine
   Kernassertion (Organisation B bleibt unberührt) abgeschwächt, entfernt oder umformuliert
   wurde.
3. Beide bestehenden Background Jobs (`approval_reminder`, `audit_log_archival`) funktionieren
   nach der Migration auf das neue API weiterhin korrekt (bestehende Tests in
   `app/jobs/test_approval_reminder.py` und `app/jobs/test_audit_log_archival.py` bleiben grün).
4. Die bestehenden Multi-Tenant-Tests (`app/test_multi_tenant_isolation.py`) bleiben grün.
5. Der neue AST-Guard erkennt zuverlässig einen absichtlich unsicheren Testhandler (der
   `app.repositories.*` direkt importiert oder einen rohen `organization_id`-/`conn`-Parameter
   annimmt) und lässt ihn nicht unbemerkt durch.
6. Alle App-Tests sind grün (vollständiger Lauf wie in `app/README.md` dokumentiert).
7. Alle bestehenden Factory-Tests sind grün (`factory.guards.test_validate_finding`,
   `factory.guards.test_run_factory_checks`, `.claude/hooks/test_stop_validate_findings.py`).
8. `python3 factory/guards/run-factory-checks.py` beendet sich mit Exit-Code 0.

## Scope

**Erlaubt:**
- Änderungen ausschließlich innerhalb von `app/jobs/` (Laufzeit-Sicherheitsgrenze, Migration
  der zwei bestehenden Handler) und ein neues Guard-Skript unter `factory/guards/` (oder
  gleichwertig, konsistent mit bestehender Guard-Konvention).
- Neue Testdateien, die genau diesen Umfang testen (Regressionstest, Guard-Test).

**Nicht erlaubt / außerhalb dieses Bauauftrags:**
- Keine Änderung am Datenbankschema (`app/db.py`).
- Keine fachliche Produktänderung (kein neues Feature, kein geänderter Ablauf für Organizations,
  Users, Suppliers, Procurement Requests, Approvals).
- Keine Änderung an `app/services/procurement_service.py` oder am interaktiven Repository-API
  (die ungebundenen Funktionen mit explizitem `organization_id`-Parameter bleiben für diesen
  Pfad unverändert bestehen).
- Keine Änderungen außerhalb von Background Jobs und Factory-Guards, die nicht unmittelbar zur
  Erfüllung der Acceptance Criteria oben nötig sind.

## Was dieser Bauauftrag ausdrücklich nicht ist

Dieser Bauauftrag enthält selbst keinen Testcode, keinen Produktionscode und keinen Guard-Code.
Er setzt `P1-DEMO-1` nicht auf `IMPLEMENTING`. Die Umsetzung beginnt erst, wenn dieser
Bauauftrag freigegeben und die Statusänderung explizit vorgenommen wird.

## Red Regression Evidence

Schritt 1 aus der verbindlichen Reihenfolge oben ist erfüllt: Es existiert ein Regressionstest,
der die Root Cause von `P1-DEMO-1` mit dem heutigen, unveränderten Produktionscode beweist. Der
Test verwendet ausschließlich bereits existierende APIs (`app.db.init_db`,
`app.repositories.*`, `app.jobs.queue.enqueue/run_pending/get_by_id`) — kein
`ScopedRepositories`, kein AST-Guard, keine Migration.

**Testdatei:** `app/jobs/test_org_scope_regression.py`
**Exakter Testname:** `app.jobs.test_org_scope_regression.TestOrgScopeRegressionP1Demo1.test_job_scoped_to_org_a_must_not_be_able_to_mutate_org_b_data`
**Exakter Befehl:**
```
python3 -m unittest app.jobs.test_org_scope_regression -v
```

**Simulierter fehlerhafter Job:** Ein Job wird über `queue.enqueue(conn, "buggy_reminder_job",
org_a.id, payload={...})` für Organisation A eingeplant und von der Job-Infrastruktur
anstandslos unter `organization_id = org_a.id` akzeptiert. Der zugehörige (bewusst fehlerhafte)
Handler `_buggy_handler_ignores_its_own_job_org` ignoriert jedoch `payload["organization_id"]`
und verwendet stattdessen `payload["acts_on_organization_id"]` (Organisation B) für einen
tenant-gebundenen Repository-Aufruf (`procurement_requests.update_status`) — ein realistischer
Stellvertreter für einen Variablen-/Copy-Paste-Fehler, wie ihn ein künftiger Handler machen
könnte.

**Erwartetes Sicherheitsverhalten:** Ein Job, den die Job-Infrastruktur selbst Organisation A
zugeordnet hat, darf niemals Daten von Organisation B verändern können. Konkret: der
`procurement_request` von Organisation B muss nach dem Job-Lauf weiterhin den Status
`submitted` haben.

**Tatsächlich beobachtetes Verhalten (heutiger Code):**
- Die Job-Infrastruktur akzeptiert den Job anstandslos unter `organization_id = org_a.id`
  (verifiziert vor dem Lauf).
- `queue.run_pending()` führt den fehlerhaften Handler aus und meldet den Job als
  `succeeded` — es gibt keine Fehlermeldung, keine Exception, keine Warnung.
- Der `procurement_request` von Organisation B wurde tatsächlich von `submitted` auf
  `approved` verändert.
- Es existiert keine zentrale technische Schranke in `app/jobs/queue.py` oder
  `app/repositories/procurement_requests.py`, die dies verhindert hätte.

**Relevante Failure-Ausgabe (Lauf vor dem Fix):**
```
FAIL: test_job_scoped_to_org_a_must_not_be_able_to_mutate_org_b_data (app.jobs.test_org_scope_regression.TestOrgScopeRegressionP1Demo1)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "app/jobs/test_org_scope_regression.py", line 97, in test_job_scoped_to_org_a_must_not_be_able_to_mutate_org_b_data
    self.assertEqual(
AssertionError: 'approved' != 'submitted'
- approved
+ submitted
 : SECURITY: a background job enqueued for Organization A was able to change Organization B's
   procurement request status from 'submitted' to 'approved'. There is no central technical
   boundary in app/jobs/queue.py or app/repositories/procurement_requests.py that prevents a
   handler from acting on a different organization than the one its job belongs to.

Ran 1 test in 0.003s

FAILED (failures=1)
```

Der Fehlschlag ist ein `AssertionError` an genau der Sicherheits-Assertion (`FAIL`), keine
Exception durch fehlenden Import, fehlende Klasse oder Syntaxfehler (`ERROR`) — der Test schlägt
ausschließlich wegen der real vorhandenen Sicherheitslücke fehl.

**Baseline-Bestätigung:** Der vollständige bestehende App-Test-Lauf (53 Tests, siehe
`app/README.md`) bleibt unverändert grün — dieser Regressionstest wurde separat und zusätzlich
ausgeführt, kein bestehender Test wurde verändert oder abgeschwächt, kein Produktionscode wurde
angefasst.

## Green Runtime Fix Evidence

Schritt 3 und 4 aus der verbindlichen Reihenfolge sind erfüllt: Die primäre
Laufzeit-Sicherheitsgrenze ist implementiert, beide bestehenden Jobs sind migriert, und
derselbe Regressionstest — mit unveränderter Sicherheits-Assertion — ist jetzt grün. Der
AST-Guard (Schritt 5) ist bewusst noch **nicht** gebaut.

### Welche Änderung die Sicherheitsgrenze erzeugt

Neue Datei `app/jobs/scoped_repositories.py`: `ScopedRepositories` ist eine Klasse, die bei
Konstruktion permanent an genau eine `organization_id` gebunden wird (`__init__(self, conn,
organization_id)`). Keine ihrer Methoden (`list_pending_procurement_requests_older_than`,
`update_procurement_request_status`, `record_audit_log`, `list_audit_log_older_than`,
`archive_audit_log_entries`, `delete_audit_log_ids`) nimmt eine `organization_id` entgegen —
die gebundene ID wird intern an die bestehenden Repository-Funktionen durchgereicht. Es ist ein
dünner Wrapper, keine Duplikation von Abfragelogik.

`app/jobs/queue.py::run_pending` konstruiert dieses Objekt jetzt zentral und **pro Job neu**,
direkt aus `row["organization_id"]` — der Spalte, die die Queue selbst beim Einplanen des Jobs
gesetzt hat, nicht aus dem Payload. Handler werden jetzt als `handler(scope, payload)`
aufgerufen statt als `handler(conn, payload)`. Ein Handler bekommt damit nie mehr eine rohe
Datenbankverbindung und nie mehr einen Parameter, über den er selbst eine `organization_id`
wählen könnte.

### Migrierte Jobs

- `app/jobs/approval_reminder.py` — `handle(scope, payload)`, kein direkter Import von
  `app.repositories.*` mehr.
- `app/jobs/audit_log_archival.py` — `handle(scope, payload)`, kein direkter Import von
  `app.repositories.*` mehr.

### Regressionstest: vorher rot, jetzt grün, unveränderte Assertion

`app/jobs/test_org_scope_regression.py::TestOrgScopeRegressionP1Demo1::test_job_scoped_to_org_a_must_not_be_able_to_mutate_org_b_data`
wurde **nur** so angepasst, dass ihr eingebetteter Test-Handler dem neuen Aufruf-Vertrag
`(scope, payload)` statt `(conn, payload)` folgt (sonst wäre der Test aus einem
Signatur-Fehler heraus fehlgeschlagen, nicht aus dem fachlich richtigen Grund). Die
Kernassertion — "Organisation B bleibt bei `submitted`" — und ihre Fehlermeldung sind
unverändert. Vor dem Fix war das Ergebnis von `request_b_after.status` `'approved'` (siehe Red
Regression Evidence oben); jetzt ist es `'submitted'`, weil `scope.update_procurement_request_status`
intern immer mit der an `scope` gebundenen `organization_id` (Organisation A) filtert und die
Zeile von Organisation B deshalb keine Treffer liefert (0 betroffene Zeilen, kein Fehler, aber
auch keine Änderung).

```
python3 -m unittest app.jobs.test_org_scope_regression -v
```
```
test_job_scoped_to_org_a_must_not_be_able_to_mutate_org_b_data (app.jobs.test_org_scope_regression.TestOrgScopeRegressionP1Demo1) ... ok

----------------------------------------------------------------------
Ran 1 test in 0.003s

OK
```

### Testergebnisse (vollständig)

```
python3 -m unittest app.jobs.test_approval_reminder app.jobs.test_audit_log_archival -v
# Ran 6 tests -> OK

python3 -m unittest app.test_multi_tenant_isolation -v
# Ran 6 tests -> OK

python3 -m unittest \
  app.test_db app.repositories.test_organizations app.repositories.test_users \
  app.repositories.test_suppliers app.repositories.test_procurement_requests \
  app.repositories.test_approvals app.repositories.test_audit_log \
  app.services.test_procurement_service app.jobs.test_queue \
  app.jobs.test_approval_reminder app.jobs.test_audit_log_archival \
  app.jobs.test_org_scope_regression app.test_multi_tenant_isolation -v
# Ran 54 tests -> OK (53 bestehende Tests + 1 Regressionstest, jetzt Teil der Baseline)

python3 factory/guards/run-factory-checks.py
# Factory-Checks: ALLE BESTANDEN
```

### Bewusst noch offen

Der AST-basierte Factory-Guard (Schritt 5) ist noch nicht gebaut. Die primäre Grenze
(`ScopedRepositories`) verhindert die *unabsichtliche* Verwendung einer fremden
`organization_id`, weil dafür schlicht kein Parameter mehr existiert. Ein *absichtlicher*
Umgehungsversuch — z. B. ein zukünftiger Handler, der `app.repositories.*` direkt importiert
oder auf das private Attribut `scope._conn` zugreift — ist damit noch nicht automatisiert
erkennbar. Das ist genau die Restlücke, die der AST-Guard in Schritt 5 schließen soll.
