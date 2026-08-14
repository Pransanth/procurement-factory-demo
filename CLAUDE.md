# Software Factory – Leitplanken für Claude

Dieses Repository ist die Grundlage einer "Software Factory": ein wiederholbarer Prozess, mit
dem Sicherheitsbefunde (und später andere technische Arbeit) kontrolliert von der Meldung bis
zum Abschluss durchlaufen — mit klaren Zuständen und einem Guard, der die Regeln unabhängig von
jeder einzelnen Claude-Anweisung durchsetzt.

## Aktueller Stand

Aktuell existiert nur die Grundlage: Workflow-Definition, ein Dummy-Befund (`P1-DEMO-1`) und ein
deterministischer Guard. Es gibt noch **keine** Procurement-Anwendung und **keinen** echten Fix
für `P1-DEMO-1`. Solange nichts anderes vereinbart ist:

- Baue keine Procurement-App.
- Analysiere oder repariere `P1-DEMO-1` nicht technisch — er ist bewusst nur ein Übungsbefund.

## Grundregel: Sicherheitsbefunde nicht direkt reparieren

Sicherheitsbefunde werden **nicht direkt repariert**. Sie durchlaufen stattdessen den
Factory-Workflow und werden erst nach abgeschlossener Analyse und Verifikation umgesetzt.
Direktes "schnell mal fixen" umgeht die Analyse-, Test- und Nachvollziehbarkeitsschritte, die der
Workflow erzwingt, und ist deshalb nicht erlaubt.

## Workflow-Zustände

```
OPEN → ANALYZED → IMPLEMENTING → VERIFYING → READY_FOR_CLOSURE → CLOSED
```

Zusätzlich existiert der Eskalationszustand `EXPERT_REVIEW_REQUIRED` (siehe unten). Die genauen
Anforderungen an jeden Zustand stehen in [`.claude/rules/factory-workflow.md`](.claude/rules/factory-workflow.md).

## Technische Entscheidungen trifft Claude selbst

Claude trifft normale technische Entscheidungen (Ursachenanalyse, Reparaturansatz, Testplan,
Guard-Design) eigenständig und begründet sie schriftlich im jeweiligen Finding. Ein
nicht-technischer Projektinhaber soll **nicht** pro forma technische Sicherheitsrisiken
freigeben müssen — das wäre keine echte Kontrolle, sondern nur ein Ritual.

## Eskalation: `EXPERT_REVIEW_REQUIRED`

Wenn Claude feststellt, dass eine autonome Entscheidung nicht verantwortbar ist (ungewöhnlich
hohes technisches Risiko, große Unsicherheit über die Auswirkungen, potenziell irreversible
Konsequenzen o. Ä.), wird der Status `EXPERT_REVIEW_REQUIRED` gesetzt. Die Factory stoppt dann an
dieser Stelle, bis ein Mensch mit der nötigen Fachkenntnis entscheidet.

## Tests und Sicherheitskontrollen dürfen nicht abgeschwächt werden

Tests oder Sicherheitskontrollen dürfen niemals abgeschwächt, übersprungen oder entfernt werden,
nur damit etwas grün wird oder ein Status schneller erreicht wird. Wenn ein Test oder eine
Kontrolle einem Fix im Weg steht, ist das ein Signal, den Fix oder die Analyse zu überdenken —
nicht die Kontrolle zu schwächen.

## Git-Routine: einfache Befehle aus dem Repo-Verzeichnis, nie `git -C <pfad>`

Alle Routine-Git-Befehle der Factory laufen als **einfache** Befehle aus dem bereits richtigen
Arbeitsverzeichnis — der Repo-Wurzel bzw. dem Worktree des jeweiligen Findings:

```
git add <pfade>
git commit -m "..."
git fetch origin
git push origin <branch>
```

Genau diese einfache Form ist allowlistet und läuft ohne Approval-Abfrage. Die Allowlist-Einträge
sind **Präfix-Muster** (`git add *`, `git commit *`, `git fetch origin`, `git push origin *`, …).
Ein vorangestelltes `-C` verschiebt den Befehlsanfang und trifft deshalb kein einziges Muster
mehr: `git -C <pfad> commit …` erzeugt eine Approval-Abfrage und bricht damit einen
unbeaufsichtigten Factory-Lauf ab. Daraus folgt:

- **Kein** `git -C <pfad> commit …`, `git -C <pfad> push …` o. Ä. für normale Finding-Arbeit.
  Stattdessen zuerst in das richtige Verzeichnis wechseln (bei paralleler Arbeit: den Worktree
  über `EnterWorktree` betreten) und dann den einfachen Befehl absetzen.
- Auch keine Ersatzkonstruktionen wie `cd <pfad> && git commit …`: zusammengesetzte Befehle,
  Subshells, Command-Substitution und Pipelines treffen die Präfix-Muster ebenso wenig und sind
  für Git-Routine generell zu vermeiden.
- Die richtige Reaktion auf eine Routine-Approval-Abfrage ist **nie**, Berechtigungen zu
  erweitern (insbesondere keine breiten Muster wie `git *` oder `git -C *`), sondern den Befehl
  in die einfache Form aus dem korrekten Arbeitsverzeichnis zu bringen.

Einzige Ausnahme: *innerhalb* eines Factory-Skripts, das ohnehin als ein einziger allowlisteter
Aufruf läuft, darf `git -C <worktree>` verwendet werden, um gezielt einen **anderen** Worktree
lesend zu prüfen — so verifiziert `create-finding-worktree.sh` den HEAD des gerade erzeugten
Worktrees. Für Befehle, die die Session selbst absetzt, gilt die Regel ausnahmslos.

## Finding-Branches: immer `--no-track`, Basis vor dem ersten Schreiben prüfen

`.git/config` ist für die Sandbox nicht schreibbar. Das ist eine gewollte Grenze und wird **nicht**
gelockert. Ein Branch, dessen Startpunkt ein Remote-Tracking-Ref (`origin/main`) ist, richtet aber
per Default Upstream-Tracking ein (`branch.autoSetupMerge`) und schreibt dafür
`branch.<name>.remote` und `branch.<name>.merge` nach `.git/config`. Das scheitert an der Sandbox
mit `could not lock config file .git/config: Operation not permitted` und lässt die
Branch-Erzeugung fehlschlagen.

Ein Finding-Branch braucht dieses Tracking nicht — gepusht wird ohnehin explizit mit
`git push origin <branch>`. Kanonisch sind deshalb vier einzelne, einfache Befehle aus dem
Repo-Verzeichnis:

```
git fetch origin
git switch --no-track -c <finding-branch> origin/main
git rev-parse HEAD
git rev-parse origin/main
```

Die beiden SHAs müssen **identisch** sein, bevor irgendetwas geschrieben wird. Bei Abweichung:
`AUTONOMY_BLOCKER: ...` melden und nicht weiterarbeiten.

Für Worktrees gilt dasselbe; dort setzt `factory/scripts/create-finding-worktree.sh` (siehe
nächster Abschnitt) `--no-track` selbst und verifiziert die Basis, bevor es den Worktree
freigibt. Beides ist durch
[`factory/guards/test_create_finding_worktree.py`](factory/guards/test_create_finding_worktree.py)
deterministisch abgesichert — inklusive des Falls, dass ein stale lokaler Branch bzw. ein
verwaister Remote-HEAD existiert und `.git/config` nicht schreibbar ist.

## Mehrere Findings gleichzeitig: Worktree statt Branch-Wechsel im selben Verzeichnis

`.claude/hooks/`, `.claude/skills/`, `.claude/agents/`, `.claude/settings.json` und
`.claude/settings.local.json` sind absichtlich vor Schreibzugriff geschützt (siehe
`.claude/settings.json` → `sandbox.filesystem.denyWrite` und `permissions.deny`) — sowohl für den
Bash-Sandbox als auch für Edit/Write. Reproduzierter Nebeneffekt: wechselt `git checkout`/`git
switch` im Hauptverzeichnis zwischen Commits, die sich in diesen Pfaden unterscheiden, kann der
Wechsel dort nicht vollständig schreiben und bricht in einem inkonsistenten Zwischenzustand ab.

Da diese Pfade jetzt für jeden künftigen Commit ausnahmslos gesperrt sind, können normale,
künftige Finding-Branches darin gar nicht mehr voneinander abweichen — reines Hin- und
Herwechseln ist damit wieder unbedenklich. Für **echt gleichzeitige** Arbeit an mehreren Findings
(z. B. zwei P1 im selben Lauf) trotzdem bevorzugt einen eigenen Worktree pro Finding-Branch
verwenden, statt im Hauptverzeichnis zwischen Branches zu wechseln — das hält beide Findings
sauber getrennt und vermeidet jede Abhängigkeit von der obigen Analyse.

**Worktree-Basis: immer explizit `origin/main`, nie EnterWorktrees impliziten "fresh"-Default.**
EnterWorktrees `fresh`-Basis-Modus (harness-seitiger Default) löst "den Default-Branch" über den
lokal gecachten Symref `refs/remotes/origin/HEAD` auf. `git fetch origin` aktualisiert diesen
Symref **nicht** — nur ein expliziter `git remote set-head` tut das. Ist er verwaist (real
beobachtet: er zeigte auf einen alten, bereits gemergten Feature-Branch statt auf
`refs/remotes/origin/main`), entsteht ein neuer Finding-Worktree still von einem veralteten
Commit statt vom aktuellen `origin/main`-Stand. EnterWorktree selbst bietet keinen Parameter für
einen expliziten Basis-Ref/SHA.

Deshalb für jeden Finding-Worktree zwingend zweistufig über
[`factory/scripts/create-finding-worktree.sh`](factory/scripts/create-finding-worktree.sh) gehen,
statt `EnterWorktree` direkt einen neuen Worktree anlegen zu lassen:

```
factory/scripts/create-finding-worktree.sh resolve
factory/scripts/create-finding-worktree.sh create <sha-aus-resolve> .claude/worktrees/<name> <branch>
```

Das sind zwei getrennte, einfache Befehle: den von `resolve` ausgegebenen SHA ablesen und im
zweiten Aufruf wörtlich einsetzen — keine Command-Substitution, keine Subshell (siehe
"Git-Routine" oben).

Das Skript fetcht `origin`, bestimmt den erwarteten Basis-SHA explizit aus `origin/main`, legt den
Worktree direkt von diesem Ref an (mit `--no-track`, siehe Abschnitt zu Finding-Branches) und
vergleicht unmittelbar danach — vor jeder weiteren
Schreiboperation — den tatsächlichen Worktree-HEAD gegen den erwarteten SHA. Bei Abweichung wird
der Worktree sofort verworfen, `AUTONOMY_BLOCKER: ...` ausgegeben und nicht weitergearbeitet. Erst
nach einem erfolgreichen `create` (Exit 0, `WORKTREE_READY ...`) den Worktree über
`EnterWorktree` mit `path: .claude/worktrees/<name>` betreten, um die Session dorthin zu
wechseln — niemals über `EnterWorktree`s `name`-Parameter, der wieder den impliziten,
symref-abhängigen `fresh`-Default verwenden würde.
