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
