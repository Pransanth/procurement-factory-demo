# Review-Artefakte

Dieses Verzeichnis enthält die Ergebnisse unabhängiger Closure-Reviews für Findings, jeweils
eine Datei pro Finding: `factory/reviews/<Finding-ID>.md` (z. B. `factory/reviews/P1-DEMO-1.md`).

Ein Review-Artefakt wird vom `finding-closure-reviewer`-Subagenten erzeugt (siehe
[`.claude/agents/finding-closure-reviewer.md`](../../.claude/agents/finding-closure-reviewer.md))
und im Rahmen des [`verify-finding`-Skills](../../.claude/skills/verify-finding/SKILL.md) hier
abgelegt. Es wird strukturell geprüft von
[`factory/guards/validate-review.py`](../guards/validate-review.py) und ist Teil des kanonischen
Runners (`python3 factory/guards/run-factory-checks.py`). Diese README-Datei selbst ist **kein**
Review-Artefakt und wird vom Guard ausdrücklich übersprungen.

## Format

Plain-Text-Felder, ein Feld pro Zeile — dieselbe Konvention wie bei
[Findings](../findings/P1-DEMO-1.md):

```
# <Finding-ID>

Finding: <Finding-ID>
Reviewer: <wer/was den Review durchgeführt hat>
Reviewed Commit: <Commit-Hash / Branch, oder Beschreibung der geprüften Diff-Basis>
Result: PASS | FAIL | EXPERT_REVIEW_REQUIRED
Root Cause Addressed: <ja/nein + Begründung>
Regression Evidence Checked: <was geprüft wurde, und wie>
Guard Evidence Checked: <was geprüft wurde, und wie>
Scope Checked: <wurde der genehmigte Bauauftrags-Scope eingehalten>
Remaining Risks: <verbleibende Risiken, oder "Keine">
Findings And Objections: <konkrete Einwände, oder "Keine">
```

Alle zehn Felder sind Pflichtfelder (nicht leer, kein Platzhalter wie `TBD`); `Result` muss
exakt einer der drei genannten Werte sein. `Finding` muss auf eine tatsächlich existierende
Datei unter `factory/findings/` verweisen.

## Was der Guard prüft — und was nicht

`validate-review.py` prüft ausschließlich Struktur: sind alle Felder ausgefüllt, ist `Result`
ein gültiger Wert, existiert das referenzierte Finding. Er bewertet **nicht**, ob der Inhalt
inhaltlich zutrifft — ob die Root Cause wirklich behoben ist, ob die Regressionsbeweise
überzeugend sind, ob es übersehene Umgehungswege gibt. Diese inhaltliche Bewertung liefert
ausschließlich der unabhängige Reviewer; ein einfacher Python-Validator kann und soll sie nicht
ersetzen.

Ein Finding kann `READY_FOR_CLOSURE` oder `CLOSED` nur erreichen, wenn sein `Review Artifact`-Feld
auf eine hier gültige Datei mit `Result: PASS` verweist — geprüft von
[`factory/guards/validate-finding.py`](../guards/validate-finding.py). `Result: FAIL` oder
`Result: EXPERT_REVIEW_REQUIRED` blockieren das technisch.
