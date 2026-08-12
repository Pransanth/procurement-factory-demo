#!/usr/bin/env python3
"""Deterministic, LLM-free structural guard for finding closure review artifacts.

Usage:
    python3 factory/guards/validate-review.py <path-to-review.md>

A review artifact is the recorded output of an independent closure review
(see .claude/agents/finding-closure-reviewer.md and
.claude/skills/verify-finding/SKILL.md) for one specific finding. This
guard checks only STRUCTURE: are all required fields present and not a
placeholder, is "Result" one of the three allowed values, and does
"Finding" point at a finding file that actually exists. It does NOT and
CANNOT judge whether the review's content is actually correct -- whether
the fix really addresses the root cause, whether the regression test
evidence is convincing, whether there are unnoticed bypass paths -- that
judgment is the independent reviewer's job, not a Python script's.

This is deliberately the mirror image of factory/guards/validate-finding.py,
which separately checks (for a finding trying to reach
READY_FOR_CLOSURE/CLOSED) that its referenced review artifact exists and
has Result: PASS, WITHOUT re-checking the review artifact's own field
completeness. That split keeps each script's job narrow and avoids
duplicating checking logic between the two.

Format (plain text, one field per line, same convention as
factory/findings/*.md):

    # <Finding ID>

    Finding: <finding ID, e.g. P1-DEMO-1>
    Reviewer: <who/what performed the review, e.g. finding-closure-reviewer subagent>
    Reviewed Commit: <commit hash / branch, or a description of the reviewed diff basis>
    Result: PASS | FAIL | EXPERT_REVIEW_REQUIRED
    Root Cause Addressed: <yes/no + justification>
    Regression Evidence Checked: <what was checked, and how>
    Guard Evidence Checked: <what was checked, and how>
    Scope Checked: <was the approved build order scope respected>
    Remaining Risks: <any risks left, or "None identified">
    Findings And Objections: <concrete objections, or "None">

No blank "## Analyse" section is required here (unlike findings) -- a
review artifact has no lifecycle of its own, it is a one-time snapshot, so
the fields are read directly from the whole file body.

Exit code 0: file is structurally valid.
Exit code 1: at least one required field is missing/a placeholder, Result
             is not one of PASS / FAIL / EXPERT_REVIEW_REQUIRED, or
             "Finding" does not point at an existing finding file.
"""
import re
import sys
from pathlib import Path

REQUIRED_REVIEW_FIELDS = [
    "Finding",
    "Reviewer",
    "Reviewed Commit",
    "Result",
    "Root Cause Addressed",
    "Regression Evidence Checked",
    "Guard Evidence Checked",
    "Scope Checked",
    "Remaining Risks",
    "Findings And Objections",
]

ALLOWED_RESULTS = {"PASS", "FAIL", "EXPERT_REVIEW_REQUIRED"}

PLACEHOLDER_VALUES = {
    "",
    "tbd",
    "todo",
    "not yet analyzed",
    "n/a",
}

FIELD_LINE_RE = re.compile(r"^([A-Za-z][A-Za-z ]*?):\s*(.*)$")

# factory/guards/validate-review.py -> parents[0]=guards, [1]=factory, [2]=repo root
REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_review(text):
    """Parse a review artifact's raw text into {field_name: value}."""
    fields = {}
    for raw_line in text.splitlines():
        match = FIELD_LINE_RE.match(raw_line.strip())
        if match:
            name, value = match.group(1).strip(), match.group(2).strip()
            fields[name] = value
    return fields


def validate_review(fields):
    """Return a list of human-readable error strings; empty list means valid."""
    errors = []

    for field_name in REQUIRED_REVIEW_FIELDS:
        value = fields.get(field_name)
        if value is None:
            errors.append(f"Pflichtfeld fehlt: '{field_name}'.")
            continue
        if value.strip().lower() in PLACEHOLDER_VALUES:
            errors.append(
                f"Pflichtfeld '{field_name}' ist leer oder ein Platzhalter ('{value}')."
            )

    result_value = fields.get("Result")
    if result_value is not None and result_value.strip().lower() not in PLACEHOLDER_VALUES:
        if result_value.strip() not in ALLOWED_RESULTS:
            errors.append(
                f"'Result' hat ungültigen Wert '{result_value}'. Erlaubt sind: "
                + ", ".join(sorted(ALLOWED_RESULTS))
            )

    finding_value = fields.get("Finding")
    if finding_value is not None and finding_value.strip().lower() not in PLACEHOLDER_VALUES:
        referenced_finding = REPO_ROOT / "factory" / "findings" / f"{finding_value.strip()}.md"
        if not referenced_finding.is_file():
            errors.append(
                f"'Finding' verweist auf '{finding_value}', aber {referenced_finding} "
                "existiert nicht."
            )

    return errors


def main(argv):
    if len(argv) != 2:
        print("Usage: validate-review.py <path-to-review.md>", file=sys.stderr)
        return 1

    path = Path(argv[1])
    if not path.is_file():
        print(f"Datei nicht gefunden: {path}", file=sys.stderr)
        return 1

    text = path.read_text(encoding="utf-8")
    fields = parse_review(text)
    errors = validate_review(fields)

    if errors:
        print(f"UNGÜLTIG: {path}", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"GÜLTIG: {path} (Result: {fields.get('Result')})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
