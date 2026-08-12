# P1-DEMO-1

Status: IMPLEMENTING

## Befund

Neue Hintergrundjobs können hinzugefügt werden, ohne dass automatisch geprüft wird, ob sie die
richtige Organisation verwenden.

Es ist kein konkreter Datenübergriff bekannt. Ein zukünftiger Job könnte jedoch versehentlich
Daten einer anderen Organisation bearbeiten.

## Analyse

Root Cause: Die Organisationstrennung wird ausschliesslich durch eine Namens-/Parameterkonvention erzwungen (jede Repository-Funktion unter app/repositories/*.py verlangt organization_id als Parameter und filtert damit, z. B. app/repositories/users.py:40-45), nicht durch eine strukturelle Grenze; ein Job-Handler erhaelt seine organization_id lediglich als Wert im eigenen JSON-Payload (app/jobs/queue.py:44-47) und muss sie bei jedem Repository-Aufruf manuell korrekt weiterreichen (Beispiel app/jobs/approval_reminder.py:28-44), ohne dass irgendeine Komponente prueft oder erzwingt, dass die tatsaechlich benutzte ID mit der des Jobs uebereinstimmt.
Affected Components: app/jobs/queue.py (enqueue, run_pending), app/jobs/handlers.py (Registry ohne Kontrolle der Org-Nutzung), die heutigen Handler app/jobs/approval_reminder.py und app/jobs/audit_log_archival.py, sowie alle org-gescopten Funktionen unter app/repositories/*.py, sobald sie von einem Handler aufgerufen werden; nicht Teil dieses Findings ist app/services/procurement_service.py (interaktiver Pfad, gleiche Grundstruktur, aber separates Thema).
Relevant Architecture: run_pending() verarbeitet in einem Lauf faellige Jobs ueber alle Organisationen hinweg (app/jobs/queue.py:63-101) und ruft dafuer HANDLERS[job_type](conn, payload) auf; organization_id steckt nur im payload-Dict, das enqueue() dafuer mit der uebergebenen ID anreichert (app/jobs/queue.py:44-47), und wird von jedem Handler eigenstaendig ausgelesen (payload["organization_id"]); es existiert kein current-org-Kontext, kein Wrapper-Objekt und keine Connection-Ebene, die die Organisation fuer die Dauer eines Jobs technisch festlegt oder gegenprueft.
Recommended Repair: Handler erhalten kuenftig statt (conn, payload) ein an genau eine organization_id gebundenes ScopedRepositories-Objekt (duenner Wrapper/Partial-Bindung ueber die bestehenden Repository-Funktionen), das ausschliesslich vom Job-Runner beim Start eines Jobs aus payload["organization_id"] konstruiert wird; Handler-Code besitzt dann gar keinen Parameter mehr, ueber den eine andere organization_id angegeben werden koennte, wodurch falsche Verwendung strukturell unmoeglich statt nur unerwuenscht wird, statt sich auf Entwicklerdisziplin zu verlassen.
Regression Test Plan: Ein bewusst fehlerhaft geschriebener Test-Handler, der versucht, Repository-Funktionen mit einer anderen als der eigenen organization_id oder unter Umgehung des ScopedRepositories-Objekts aufzurufen, muss vor dem Fix eine Cross-Org-Datenveraenderung zeigen (roter Test, der die Fehlerklasse belegt) und nach dem Fix entweder gar nicht mehr aufrufbar sein oder vom neuen zentralen Guard automatisch abgelehnt werden (gruener Test); ergaenzend zu den bestehenden Isolationstests in app/test_multi_tenant_isolation.py, die bisher nur den korrekten Pfad pruefen, nicht den Missbrauchsfall.
Central Guard Plan: Ein neues, deterministisches Guard-Skript nach dem Vorbild von factory/guards/validate-finding.py (kein LLM, reines Python, AST-basiert statt Regex) prueft jede unter HANDLERS registrierte Handler-Datei in app/jobs/ darauf, dass sie app.repositories.* nicht direkt importiert und keinen rohen organization_id- oder conn-Parameter annimmt, sondern ausschliesslich ueber das ScopedRepositories-Objekt auf Daten zugreift, und wird in denselben Pruefpfad (lokal, Stop-Hook, CI) wie die bestehenden Factory-Guards eingehaengt, sodass ein Verstoss automatisch erkannt statt nur per Konvention vermieden wird.
Expected Blast Radius: Heute ist niemand betroffen, da beide bestehenden Handler die organization_id korrekt aus dem eigenen Payload lesen (siehe app/test_multi_tenant_isolation.py, insbesondere test_job_run_with_correct_org_id_only_touches_its_own_org); die Reparatur selbst betrifft ausschliesslich app/jobs/ (queue.py, handlers.py, approval_reminder.py, audit_log_archival.py) plus ein neues Guard-Skript, keine Datenbankschema-Aenderung und keine Auswirkung auf app/services/procurement_service.py oder die bestehenden Repository-Signaturen des interaktiven Pfads.
Risk Assessment: Das Risiko des Nichtstuns ist strukturell real (ein zukuenftiger Handler koennte unbemerkt auf falsche Organisationsdaten zugreifen), aber aktuell ohne bekannten konkreten Schaden; das Risiko der vorgeschlagenen Reparatur ist gering und gut eingrenzbar, da sie additiv ist (neues Wrapper-Objekt, neuer Guard, angepasste Handler-Signatur fuer nur zwei bestehende, gut getestete Handler) und weder Schema noch interaktiven Pfad veraendert; insgesamt eine normale, autonom vertretbare technische Entscheidung ohne irreversible Konsequenzen.
Expert Review Reason: Not yet analyzed
What Is Known: Not yet analyzed
What Remains Uncertain: Not yet analyzed
What An Expert Would Need To Review: Not yet analyzed
