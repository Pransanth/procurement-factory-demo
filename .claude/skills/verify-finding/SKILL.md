---
name: verify-finding
description: Drive a factory finding through IMPLEMENTING -> VERIFYING -> independent review -> READY_FOR_CLOSURE -> CLOSED. Use when a finding's fix is implemented and its gates (regression test, relevant tests, guards, canonical runner, CI) need to be verified and an independent review obtained before closure.
argument-hint: [finding-id]
disable-model-invocation: true
---

This skill is the standardized, reusable procedure for verifying and closing a factory finding.
It does not invent security judgments itself — it systematically checks existing evidence
(finding, build order, tests, guards, CI) and delegates the actual security judgment to the
independent `finding-closure-reviewer` subagent. If you find yourself deciding "this looks fine"
on your own authority instead of citing a passed gate or the reviewer's verdict, stop — that is
exactly the shortcut this skill exists to prevent.

Argument: a finding ID (e.g. `P1-DEMO-1`). Its file is `factory/findings/<ID>.md`, its build
order (if any) is `factory/build-orders/<ID>.md`.

## Preconditions

- The finding's status must be `IMPLEMENTING` (to start this procedure) or already `VERIFYING`
  (to resume it). If it is anything else, stop and tell the user — this skill does not analyze
  findings or start implementation, see the finding's own workflow rules
  (`.claude/rules/factory-workflow.md`).
- Read the finding file and its build order in full before doing anything else.

## Step 1 — IMPLEMENTING → VERIFYING: collect gate evidence

Set `Status: VERIFYING` if not already there. Then run, and record the *actual* result of, each
of these gates — do not claim a gate passed without having just run it:

1. **Regression test** named in the finding's Regression Test Plan / the build order — must be
   green now (it was proven red before the fix; re-confirm it is green now).
2. **Relevant existing tests** — the test groups the build order identifies as touched by the
   fix (e.g. the affected module's own tests, cross-cutting isolation tests).
3. **Security/architecture guard(s)** the build order's Central Guard Plan describes (e.g. an
   AST guard) — run it directly against the relevant files, not just via the canonical runner.
4. **Canonical factory runner**: `python3 factory/guards/run-factory-checks.py` — must exit 0.
5. **External CI**: this repository denies `Bash(git push *)` and `Bash(gh *)` by default
   (`.claude/settings.json`) — you cannot push or query GitHub Actions yourself without the
   user's explicit authorization. Do not fabricate or assume a green CI run. Either ask the user
   to confirm a specific CI run (URL or run ID) is green, or explicitly ask for authorization to
   push and check it yourself; record whichever actually happened.

Write what you found into the finding's `## Analyse` section as `Verification Evidence` (a
concise summary of gates 1–3 with concrete test/guard names and outcomes) and `CI Evidence`
(the concrete CI run reference from gate 5, or a clear note that it is still outstanding — do
not fill this field with anything you didn't actually confirm).

If any gate fails: stop here, report the failure, and do not proceed to review. A finding with a
red gate is not ready for independent review.

## Step 2 — Independent review

Use the Agent tool with `subagent_type: finding-closure-reviewer` to run the review in a
genuinely separate context. The reviewer has no memory of this conversation and read-only tools
(Read, Grep, Glob) — it cannot run commands or see a live diff unless you give it one. In the
prompt, include:
- The finding ID and path, and the build order path.
- What changed: ideally the actual diff (`git diff` / `git log`, gathered by you beforehand,
  since the reviewer cannot run Bash) or, at minimum, an explicit list of changed files.
- The diff basis to record as `Reviewed Commit`: a commit hash if committed, otherwise a clear
  statement like "uncommitted working tree changes since commit `<hash>`".
- Explicit instruction to check the ten points listed in its own agent definition and to end
  with exactly one of `PASS` / `FAIL` / `EXPERT_REVIEW_REQUIRED`, formatted as the field block
  described there.

**Hard rule: you must not rewrite, soften, or reinterpret the reviewer's `Result`.** You no
longer transcribe it at all — see Step 3. If you disagree with the verdict, say so to the user —
do not silently override it. Re-invoking the reviewer to "try again" hoping for a different
answer defeats its independence; only re-invoke it if you are giving it materially new
information (e.g. you fixed something it flagged) and are running an entirely new review round.

## Step 3 — Confirm the review artifact the hook produced

You do not write `factory/reviews/<ID>.md` yourself anymore. The moment the reviewer subagent in
Step 2 finishes, a `SubagentStop` hook
(`.claude/hooks/subagentstop-write-review.py`) fires automatically: it reads the real Claude Code
event data for that subagent run (`agent_type`, `agent_id`, `last_assistant_message`) and writes
`factory/reviews/<ID>.md` directly from it — never from your own memory or summary of what the
reviewer said. `factory/reviews/` is also denied to the `Edit`/`Write` tools in
`.claude/settings.json`, so you cannot create or modify a review artifact there even if you tried.

After the Agent tool call in Step 2 returns, confirm what the hook actually produced — do not
assume it worked:
```
python3 factory/guards/validate-review.py factory/reviews/<ID>.md
```
- If `factory/reviews/<ID>.md` doesn't exist, or this command fails: the reviewer's answer either
  didn't come from the expected agent type, was malformed (missing field, ambiguous or invalid
  `Result` value, wrong number of fenced blocks), or was otherwise rejected by the hook — the hook
  deliberately never writes a `PASS` artifact from unparseable input. Read the reviewer's actual
  response to understand what went wrong, then either fix the reviewer's prompt/format guidance
  and get a fresh answer (a new review round, not a retry of the same one), or escalate. **Never
  hand-author or patch the review artifact yourself** — if the hook didn't produce it, it isn't a
  valid review artifact, full stop.
- If it validates: proceed to Step 4. The `Result` you act on there is read from this file, which
  by construction matches the hook's SubagentStop capture, not any restatement by you.

## Step 4 — Act on the verdict

- **Result: FAIL** — Do not touch the finding's status beyond where it already is (stay at
  `VERIFYING`). Report the reviewer's objections to the user. Closure is blocked by
  `factory/guards/validate-finding.py` regardless (it requires `Result: PASS`), but do not even
  attempt `READY_FOR_CLOSURE` — surface the objections and let a human decide the next step.
- **Result: EXPERT_REVIEW_REQUIRED** — Set the finding's `Status: EXPERT_REVIEW_REQUIRED` and
  fill its five required fields (`Risk Assessment`, `Expert Review Reason`, `What Is Known`,
  `What Remains Uncertain`, `What An Expert Would Need To Review`) using the reviewer's stated
  remaining risks and objections as the basis. Stop; this is a human decision point per
  `CLAUDE.md`.
- **Result: PASS** — proceed to Step 5.

## Step 5 — VERIFYING → READY_FOR_CLOSURE

Fill in `Review Artifact: factory/reviews/<ID>.md` (relative to the repo root) in the finding's
`## Analyse` section alongside the `Verification Evidence` and `CI Evidence` already written in
Step 1. Set `Status: READY_FOR_CLOSURE`. Validate:
```
python3 factory/guards/validate-finding.py factory/findings/<ID>.md
python3 factory/guards/run-factory-checks.py
```
Both must pass. If they don't, the guard is telling you something concrete is still missing or
inconsistent (e.g. a CI Evidence field left as a placeholder, or the review artifact's Result
isn't PASS) — fix that specific thing, do not work around the guard.

## Step 6 — READY_FOR_CLOSURE → CLOSED

A normal finding (no outstanding `EXPERT_REVIEW_REQUIRED`, `FAIL`, or unresolved high-risk
objection) may be set to `Status: CLOSED` directly once `READY_FOR_CLOSURE` validates — this
does not require separate human sign-off beyond the independent review already obtained, per
`CLAUDE.md`'s principle that Claude makes normal technical decisions itself. Re-run both
commands from Step 5 to confirm `CLOSED` also validates (it requires everything
`READY_FOR_CLOSURE` does, deterministically enforced).

This skill never commits or pushes on its own — that remains a separate, explicit user request
per the repository's general working rules.
