# Dummy-Procurement-App

Kleine, lernbare B2B-Procurement-SaaS als Untersuchungsobjekt für die Software Factory. Reine
Python-3-Standardbibliothek (`sqlite3` als Storage), keine externen Abhängigkeiten, kein Web-/UI-
Layer.

## Struktur

- `db.py` — Schema (SQLite) und `init_db()`.
- `models.py` — Dataclasses für die Tabellenzeilen.
- `repositories/` — eine Datei pro fachlichem Konzept (Organizations, Users, Suppliers,
  Procurement Requests, Approvals, Audit Log). Jede org-gebundene Funktion verlangt explizit
  `organization_id` und filtert konsequent darauf.
- `services/procurement_service.py` — orchestriert Repositories für mehrstufige Abläufe
  (erstellen → einreichen → entscheiden) inklusive Audit-Log-Einträgen.
- `services/user_admin_service.py` — Benutzerverwaltung innerhalb einer Organisation
  (Rollenwechsel), inklusive Audit-Log-Eintrag.
- `services/reporting_service.py` — rein lesende Auswertungen (Monatsbericht über genehmigte
  Beschaffungen). Formuliert seine Abfragen selbst, weil die Repository-Schicht bewusst keine
  Aggregation (`COUNT`, `SUM`, `ORDER BY ... LIMIT`, Joins) anbietet.
- `jobs/` — Background-Job-Subsystem: `queue.py` (Queue), `handlers.py` (Registry
  `job_type -> Funktion`), sowie zwei konkrete Jobs (`approval_reminder.py`,
  `audit_log_archival.py`). Jeder Handler liest `organization_id` aus seinem eigenen Payload —
  es gibt keinen zentralen, automatisch erzwungenen Tenant-Kontext.

## Tests ausführen

```
python3 -m unittest \
  app.test_db \
  app.repositories.test_organizations \
  app.repositories.test_users \
  app.repositories.test_suppliers \
  app.repositories.test_procurement_requests \
  app.repositories.test_approvals \
  app.repositories.test_audit_log \
  app.services.test_procurement_service \
  app.services.test_user_admin_service \
  app.services.test_reporting_service \
  app.jobs.test_queue \
  app.jobs.test_approval_reminder \
  app.jobs.test_audit_log_archival \
  app.test_multi_tenant_isolation \
  -v
```

## Nicht-Ziele dieser Runde

- Kein Web-/HTTP-Layer, keine UI.
- Kein zentraler Enforcement-Mechanismus für den Organisationskontext in Background Jobs — das
  ist bewusst offen gelassen und Gegenstand von `factory/findings/P1-DEMO-1.md`.
- Keine adversariale Regressionstests für P1-DEMO-1 (z. B. ein Job mit falscher
  `organization_id`) — das ist für nach der Analyse dieses Findings reserviert.
- Ebenso keine adversarialen Regressionstests für `factory/findings/P1-DEMO-4.md` und
  `factory/findings/P1-DEMO-5.md`. `services/test_reporting_service.py` und
  `services/test_user_admin_service.py` sind Baseline-Tests des jeweils normalen Ablaufs; die
  Gegenprobe ist für nach der Analyse dieser Findings reserviert.
