# Factory – kurze technische Einführung

Diese Datei erklärt in einfachen Worten, was die Bausteine in diesem Verzeichnis tun und wie sie
zusammenhängen. Für die genauen Zustandsregeln siehe
[`.claude/rules/factory-workflow.md`](../.claude/rules/factory-workflow.md).

## Was ist ein Finding?

Ein Finding ist eine einzelne Markdown-Datei unter `factory/findings/`, z. B.
[`P1-DEMO-1.md`](findings/P1-DEMO-1.md). Sie beschreibt einen Befund (aktuell nur
Sicherheitsbefunde) und trägt einen Status (`OPEN`, `ANALYZED`, ... siehe Workflow-Regeln). Je
nach Status müssen bestimmte Analysefelder ausgefüllt sein.

## Was ist ein Validator?

Ein Validator ist ein kleines, deterministisches Skript, das eine einzelne Finding-Datei gegen
die Regeln für ihren Status prüft — ohne KI, ohne Netzwerk, rein regelbasiert. Der aktuelle
Validator ist [`factory/guards/validate-finding.py`](guards/validate-finding.py):

```
python3 factory/guards/validate-finding.py factory/findings/P1-DEMO-1.md
```

Exit 0 = das Finding ist für seinen Status gültig, Exit 1 = ungültig (mit Fehlerliste). Er prüft
genau eine Datei und weiß nichts von anderen Findings oder davon, wer ihn aufruft.

## Was ist der gemeinsame Factory-Runner?

[`factory/guards/run-factory-checks.py`](guards/run-factory-checks.py) ist der **eine
kanonische Einstiegspunkt** für "sind alle Factory-Prüfungen aktuell grün?":

```
python3 factory/guards/run-factory-checks.py
```

Exit 0 = alle Checks bestanden, Exit 1 = mindestens einer fehlgeschlagen — mit einer klaren
Auflistung, welcher Check bei welcher Datei fehlgeschlagen ist. Er führt aktuell drei Arten von
Check aus, alle ohne KI, ohne Netzwerk, rein regelbasiert:

1. **Finding-Validierung**: jede Datei unter `factory/findings/` gegen
   [`validate-finding.py`](guards/validate-finding.py). Für ein Finding, das `READY_FOR_CLOSURE`
   oder `CLOSED` erreichen will, prüft dieser Schritt zusätzlich strukturell, dass das
   referenzierte Review-Artefakt existiert und `Result: PASS` enthält (siehe "Verification Skill
   und unabhängiger Reviewer" weiter unten).
2. **Job-Handler-Scope-Guard**: jede Datei unter `app/jobs/` gegen
   [`validate-job-handler-scope.py`](guards/validate-job-handler-scope.py) — ein AST-basierter
   Guard, der prüft, dass ein Background-Job-Handler die in
   [`factory/findings/P1-DEMO-1.md`](findings/P1-DEMO-1.md) beschriebene
   `ScopedRepositories`-Grenze nicht umgeht (z. B. durch direkten Import von
   `app.repositories.*`, einen wieder freigegebenen `organization_id`-/`conn`-Parameter, oder
   Zugriff auf `scope._conn`). Dieser Guard ist eine **zusätzliche** Schranke — die eigentliche
   Sicherheitsgrenze ist die Laufzeit-Architektur (`ScopedRepositories`), nicht dieser Guard.
3. **Review-Guard**: jede Datei unter `factory/reviews/` (außer `README.md`) gegen
   [`validate-review.py`](guards/validate-review.py) — prüft nur die Struktur eines
   Review-Artefakts (alle Felder ausgefüllt, `Result` ein gültiger Wert), nicht dessen
   inhaltliche Richtigkeit.

Künftige Checks würden ebenfalls von hier aus laufen, statt an mehreren Stellen eigene
Prüflogik zu duplizieren.

## Verification Skill und unabhängiger Reviewer

Der Weg von `IMPLEMENTING` über `VERIFYING`, ein unabhängiges Review, `READY_FOR_CLOSURE` bis
`CLOSED` ist standardisiert und wiederverwendbar, nicht an einen einmaligen Chat-Prompt
gebunden:

- **[`.claude/skills/verify-finding/SKILL.md`](../.claude/skills/verify-finding/SKILL.md)**
  beschreibt den Ablauf: Evidence einsammeln (Regressionstest, relevante Tests, Guard,
  kanonischer Runner, externe CI), unabhängiges Review anstoßen, Review-Artefakt verfassen, je
  nach Ergebnis weiter zu `READY_FOR_CLOSURE`/`CLOSED`, zu `EXPERT_REVIEW_REQUIRED`, oder
  stoppen. Der Skill trifft selbst keine Sicherheitsentscheidung — er prüft vorhandene Evidence
  systematisch und delegiert die eigentliche Bewertung an den Reviewer.
- **[`.claude/agents/finding-closure-reviewer.md`](../.claude/agents/finding-closure-reviewer.md)**
  ist ein eigenständiger, **rein lesender** Subagent (Tools: nur `Read`, `Grep`, `Glob` — kein
  `Edit`, `Write`, `Bash`). Er läuft in einem getrennten Kontext ohne Erinnerung an die
  implementierende Session und liefert genau eines: `PASS`, `FAIL` oder
  `EXPERT_REVIEW_REQUIRED`, mit Begründung und Fundstellen. Der implementierende Agent darf
  dieses Ergebnis nicht nachträglich überschreiben.
- **[`factory/reviews/`](../factory/reviews/README.md)** ist der Ort für Review-Artefakte
  (`factory/reviews/<Finding-ID>.md`), strukturell geprüft von `validate-review.py`.

**Implementierender Agent vs. unabhängiger Reviewer:** Der implementierende Agent (der die
Reparatur baut und den `verify-finding`-Skill ausführt) hat vollen Werkzeugzugriff, kennt die
gesamte Implementierungshistorie und hat naturgemäß ein Interesse daran, dass sein eigener Fix
funktioniert. Der Reviewer ist bewusst das Gegenteil: werkzeugbeschränkt (rein lesend), ohne
Gedächtnis der Implementierung, ausschließlich mit dem beauftragt, kritisch zu prüfen, ob die
Behauptungen tatsächlich stimmen. Diese Trennung ist der Grund, warum Closure-Gates (siehe
`.claude/rules/factory-workflow.md`) ein `Result: PASS` aus einem echten, separaten Review
verlangen, statt sich auf die Selbstauskunft des implementierenden Agenten zu verlassen.

## Was macht der Stop-Hook?

[`.claude/hooks/stop-validate-findings.py`](../.claude/hooks/stop-validate-findings.py) ist ein
Claude-Code-Stop-Hook: Er wird automatisch aufgerufen, wenn Claude versucht, eine Aufgabe in
diesem Repository zu beenden. Er enthält **keine eigene Prüflogik** — er ruft ausschließlich den
gemeinsamen Runner (`run-factory-checks.py`) auf und übersetzt dessen Ergebnis in das, was
Claude Code von einem Stop-Hook erwartet: bei Erfolg darf Claude stoppen, bei einem
fehlgeschlagenen Check wird der Stopp blockiert und Claude bekommt die Fehlermeldung als Grund
mitgeteilt.

## Was kann der Stop-Hook ausdrücklich NICHT garantieren?

Der Stop-Hook ist ein **lokaler Workflow-Guard**, **kein finales Security- oder Merge-Gate**.
Insbesondere:

- Er läuft nur, wenn Claude Code selbst versucht zu stoppen — er prüft nichts, wenn Dateien auf
  anderem Weg geändert werden (manuell, durch ein anderes Tool, durch ein Skript).
- Ein erster, ungültiger Stop-Versuch wird blockiert, mit der konkreten Ursache. Ein
  **wiederholter** Versuch (`stop_hook_active: true`) wird dagegen bewusst **nicht** erneut
  geprüft und **nicht** erneut blockiert — er lässt Claude sofort weiterlaufen, unabhängig davon,
  ob der Zustand inzwischen tatsächlich gültig ist. Das ist eine bewusste Verhaltensänderung:
  Eine frühere Version dieses Hooks prüfte bei jedem Versuch erneut und verließ sich auf Claude
  Codes eigenen, dokumentierten Block-Cap (nominell 8 aufeinanderfolgende Blockierungen ohne
  Fortschritt, konfigurierbar über `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`), um eine echte
  Endlosschleife zu verhindern. In der Praxis griff dieser Cap nicht zuverlässig — eine Sitzung
  blieb über viele Wiederholungen hinweg blockiert hängen, ohne dass der Cap eingriff, und ohne
  lokale Möglichkeit, das anders als durch manuelles Eingreifen außerhalb der Session zu beheben.
  Sich auf einen Plattform-Cap zu verlassen, der nicht zuverlässig greift, ist keine echte
  Schleifensicherheit. Dieser Hook liefert deshalb seine eigene, einfache Garantie: höchstens eine
  Blockierung pro Aufgabe.

  Das bedeutet auch: Ein zweiter Stop-Versuch kommt immer durch, selbst wenn der Zustand
  tatsächlich weiterhin ungültig ist. Das schwächt **keine** der eigentlichen Prüfregeln —
  `validate-finding.py`, `validate-review.py` und `run-factory-checks.py` selbst bleiben
  unverändert scharf. Es ändert nur, ob *dieser lokale Hook* einen zweiten Versuch aufhält. Ob ein
  Finding wirklich abschließbar ist, entscheiden weiterhin ausschließlich die deterministischen
  Guards und, verbindlich, GitHub CI.
- Er läuft mit den Rechten des lokalen Nutzers und lässt sich durch Konfiguration umgehen oder
  deaktivieren (z. B. Hooks überspringen, Einstellungen ändern). Ein Nutzer mit
  Schreibzugriff auf `.claude/settings.json` kann ihn jederzeit abschalten.
- Er prüft nur formale Vollständigkeit der Finding-Felder, nicht deren inhaltliche Richtigkeit.

Ein wirklich verlässliches Gate — z. B. bevor Code in einen geschützten Branch gelangt — braucht
eine serverseitige Prüfung (CI), die nicht vom lokalen Rechner, von Claude Code oder von diesem
Hook abhängt. Genau das ist GitHub CI (`.github/workflows/factory-ci.yml`): Sie läuft unabhängig
von jeder Claude-Code-Sitzung und lässt sich nicht dadurch umgehen, dass eine lokale Aufgabe (mit
oder ohne Stop-Hook-Blockierung) beendet wird. Das ist die eigentliche, externe Schranke dieses
Repos — der Stop-Hook ist bewusst nur eine lokale Arbeitshilfe während einer laufenden Session,
kein Ersatz dafür. (Ein Branch-Schutz mit Required Status Check, der einen fehlgeschlagenen
CI-Lauf tatsächlich verbindlich macht, ist noch nicht konfiguriert — CI prüft aktuell, blockiert
aber noch keinen Merge; das bleibt ein offener Schritt außerhalb dieser Sitzung.)

## Shared vs. local Claude settings

Dieses Repo hat zwei getrennte Claude-Code-Einstellungsdateien mit bewusst unterschiedlichem
Zweck:

- **`.claude/settings.json`** ist die **übertragbare, versionierte Factory-Konfiguration**. Sie
  gehört zur Vorlage selbst: der Stop-Hook und generische Demo-Schutzregeln (aktuell
  `Bash(docker *)`, `Bash(git push *)`, `Bash(gh *)` verboten), die für jede Kopie dieses Repos
  gleichermaßen sinnvoll sind. Diese Datei wird committet.
- **`.claude/settings.local.json`** ist **persönlich/maschinenspezifisch** und **niemals Teil der
  Factory-Vorlage**. Hier stehen Regeln, die nur auf dem konkreten Rechner der jeweiligen Person
  Sinn ergeben — zum Beispiel absolute Pfade zu anderen, lokalen Projekten auf derselben
  Maschine (in diesem Fall: die Isolation gegenüber einem anderen lokalen Projekt namens
  ein anderes lokales Projekt). Diese Datei wird **nicht** committet (siehe `.gitignore`).

Faustregel: **Absolute Pfade zu irgendetwas außerhalb dieses Repos gehören ausschließlich in
`settings.local.json`.** Wird dieses Repo als Vorlage für ein echtes Projekt kopiert, kann
`settings.json` unverändert mitgenommen werden — `settings.local.json` dagegen ist per Definition
für jede Maschine neu und individuell einzurichten (oder wegzulassen).

## Die Prüfkette: lokal bis CI

Es gibt vier Schichten, aber nur **eine** Prüflogik pro Check-Art — jede Schicht ruft nur die
davor auf, niemand implementiert die Regeln ein zweites Mal:

```
lokale Validatoren           factory/guards/validate-finding.py, validate-job-handler-scope.py,
                              validate-review.py                    (pruefen je 1 Datei)
        ↓
gemeinsamer Factory-Runner   factory/guards/run-factory-checks.py   (ruft alle drei fuer alle
                                                                      betroffenen Dateien auf)
        ↓
Claude Stop-Hook             .claude/hooks/stop-validate-findings.py (ruft den Runner beim Stop-Versuch auf)
        ↓
GitHub CI                    .github/workflows/factory-ci.yml        (ruft denselben Runner-Befehl in GitHub Actions auf)
```

Der Stop-Hook hilft **Claude**, lokal innerhalb einer laufenden Session korrekt zu arbeiten — er
ist an das Claude-Code-Stop-Ereignis gekoppelt und hat, wie oben beschrieben, eine bewusste
technische Grenze: Er blockiert einen ungültigen Zustand höchstens einmal pro Aufgabe, nicht
wiederholt.

**Die GitHub-CI (`factory-ci.yml`) ist davon komplett unabhängig.** Sie kennt keine Claude-Session,
keinen Stop-Hook und kein `stop_hook_active` — sie checkt bei jedem Push auf `main` und bei jedem
Pull Request gegen `main` den Repository-Zustand frisch aus und lässt exakt denselben Befehl
laufen, den auch der Stop-Hook und jeder Entwickler lokal ausführen können:

```
python3 factory/guards/run-factory-checks.py
```

Damit prüft CI **denselben Zustand ein zweites Mal, unabhängig davon, ob oder wie der Stop-Hook
lokal reagiert hat** — auf einem frischen GitHub-Actions-Runner, ohne Secrets, ohne Schreibrechte,
ohne Docker, ohne Claude-/Anthropic-API. Das ist die Absicherung dafür, dass "lokal grün" (oder
"vom Stop-Hook durchgelassen") tatsächlich auch "in CI grün" bedeutet — unabhängig davon, ob der
lokale Rechner, die Claude-Session oder der Stop-Hook selbst kompromittiert, deaktiviert oder
falsch konfiguriert wäre.
