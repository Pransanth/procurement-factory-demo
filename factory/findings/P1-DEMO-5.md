# P1-DEMO-5

Status: OPEN

## Befund

`app/services/user_admin_service.py:change_user_role` entscheidet über die Berechtigung zum Ändern
von Benutzerrollen anhand einer Ausschlussprüfung: abgelehnt wird nur, wer die Rolle `member` hat
(`if actor.role == "member": raise ValueError(...)`). Jede andere Rolle passiert die Prüfung. Ein
Benutzer mit der Rolle `approver` — im Datenmodell (`app/db.py`, `users.role CHECK(role IN
('member', 'approver', 'admin'))`) die mittlere, nicht die administrative Rolle — kann damit
Rollen innerhalb seiner Organisation vergeben, einschließlich der Rolle `admin`, und
einschließlich der Vergabe an sich selbst.

Die Organisationsgrenze ist dabei intakt: Akteur und Ziel werden über
`app/repositories/users.py:get_by_id` org-gescoped aufgelöst, ein Benutzer einer fremden
Organisation wird nicht gefunden. Der Befund ist also keine Tenant-Isolation-Verletzung, sondern
eine Rechteausweitung *innerhalb* eines Mandanten: aus `approver` wird `admin`, dauerhaft und
über den regulären Aufrufpfad.

Reproduktion (gegen eine frische In-Memory-DB via `app/db.py:init_db`):

```python
from app.db import init_db
from app.repositories import organizations, users
from app.services import user_admin_service

conn = init_db(":memory:")
org = organizations.create(conn, "Acme Corp")
carol = users.create(conn, org.id, "carol@acme.example", "Carol", "approver")

updated = user_admin_service.change_user_role(conn, org.id, carol.id, carol.id, "admin")
# updated.role == "admin" -- Carol hat sich selbst zum Administrator gemacht.
# Kein Fehler, keine Ablehnung; der Vorgang wird zusaetzlich als
# audit_log-Eintrag "user.role_changed" als regulaere Administration verbucht.
```

Das bestehende Testset zu diesem Modul (`app/services/test_user_admin_service.py`) deckt den Fall
nicht ab: es prüft, dass ein `admin` Rollen vergeben darf, dass ein `member` abgewiesen wird, dass
unbekannte Rollenwerte abgelehnt werden und dass die Organisationsgrenze hält — aber nicht, welche
Rollen zwischen `member` und `admin` die Prüfung passieren, und nicht, was beim Ändern der eigenen
Rolle geschieht.

Dies betrifft einen anderen Codepfad als P1-DEMO-1 (Job-Handler), P1-DEMO-2 (Anlegen einer
Anfrage) und P1-DEMO-3 (Entscheidung über eine Anfrage in
`app/repositories/approvals.py:record_decision`) und ist unabhängig von P1-DEMO-4: hier geht es um
die Benutzerverwaltung (`users`-Tabelle) im Schreibpfad, nicht um Beschaffungsdaten und nicht um
einen Lesepfad.

## Analyse

Root Cause: Not yet analyzed
Affected Components: Not yet analyzed
Relevant Architecture: Not yet analyzed
Recommended Repair: Not yet analyzed
Regression Test Plan: Not yet analyzed
Central Guard Plan: Not yet analyzed
Expected Blast Radius: Not yet analyzed
Risk Assessment: Not yet analyzed
Expert Review Reason: Not yet analyzed
What Is Known: Not yet analyzed
What Remains Uncertain: Not yet analyzed
What An Expert Would Need To Review: Not yet analyzed
