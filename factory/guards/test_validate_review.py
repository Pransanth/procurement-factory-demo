"""Tests for validate-review.py.

Run with:
    python3 -m unittest factory.guards.test_validate_review

Like test_validate_finding.py, this invokes the guard as a subprocess
against temporary fixture files -- never against a real file under
factory/reviews/.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "validate-review.py"

# P1-DEMO-1 genuinely exists in this repo (factory/findings/P1-DEMO-1.md),
# so it is used as the "Finding" value in valid fixtures below -- this is a
# read-only existence check, never a mutation of that file.
VALID_REVIEW = """\
# P1-DEMO-1

Finding: P1-DEMO-1
Reviewer: finding-closure-reviewer subagent
Reviewer Agent Type: finding-closure-reviewer
Reviewer Agent ID: agent-test-0001
Reviewed Commit: working tree at abc123, uncommitted changes included
Result: PASS
Root Cause Addressed: Ja -- ScopedRepositories entfernt die frei waehlbare organization_id.
Regression Evidence Checked: app/jobs/test_org_scope_regression.py gelesen, Assertion unveraendert.
Guard Evidence Checked: factory/guards/validate-job-handler-scope.py gelesen und Negativtest bestaetigt.
Scope Checked: Nur app/jobs/ und factory/guards/ veraendert, wie im Bauauftrag vereinbart.
Remaining Risks: Absichtliche Umgehung ueber dynamische Attribute bleibt technisch moeglich.
Findings And Objections: Keine.
"""

MISSING_FIELDS = """\
# P1-DEMO-1

Finding: P1-DEMO-1
Result: PASS
"""

INVALID_RESULT_VALUE = """\
# P1-DEMO-1

Finding: P1-DEMO-1
Reviewer: finding-closure-reviewer subagent
Reviewer Agent Type: finding-closure-reviewer
Reviewer Agent ID: agent-test-0001
Reviewed Commit: abc123
Result: LOOKS_GOOD_TO_ME
Root Cause Addressed: Ja.
Regression Evidence Checked: Ja.
Guard Evidence Checked: Ja.
Scope Checked: Ja.
Remaining Risks: Keine.
Findings And Objections: Keine.
"""

UNKNOWN_FINDING_REFERENCE = """\
# P9-DOES-NOT-EXIST

Finding: P9-DOES-NOT-EXIST
Reviewer: finding-closure-reviewer subagent
Reviewer Agent Type: finding-closure-reviewer
Reviewer Agent ID: agent-test-0001
Reviewed Commit: abc123
Result: PASS
Root Cause Addressed: Ja.
Regression Evidence Checked: Ja.
Guard Evidence Checked: Ja.
Scope Checked: Ja.
Remaining Risks: Keine.
Findings And Objections: Keine.
"""

VALID_FAIL_RESULT = VALID_REVIEW.replace("Result: PASS", "Result: FAIL")
VALID_EXPERT_REVIEW_RESULT = VALID_REVIEW.replace("Result: PASS", "Result: EXPERT_REVIEW_REQUIRED")

PLACEHOLDER_FIELD = VALID_REVIEW.replace(
    "Remaining Risks: Absichtliche Umgehung ueber dynamische Attribute bleibt technisch moeglich.",
    "Remaining Risks: TBD",
)

MISSING_REVIEWER_PROVENANCE = VALID_REVIEW.replace(
    "Reviewer Agent Type: finding-closure-reviewer\nReviewer Agent ID: agent-test-0001\n", ""
)

WRONG_REVIEWER_AGENT_TYPE = VALID_REVIEW.replace(
    "Reviewer Agent Type: finding-closure-reviewer",
    "Reviewer Agent Type: main-agent",
)


class ValidateReviewTests(unittest.TestCase):
    def run_guard(self, content):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as handle:
            handle.write(content)
            temp_path = handle.name
        try:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), temp_path],
                capture_output=True,
                text=True,
            )
        finally:
            Path(temp_path).unlink()
        return result

    def test_valid_review_with_result_pass(self):
        result = self.run_guard(VALID_REVIEW)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GÜLTIG", result.stdout)
        self.assertIn("PASS", result.stdout)

    def test_valid_review_with_result_fail(self):
        result = self.run_guard(VALID_FAIL_RESULT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GÜLTIG", result.stdout)

    def test_valid_review_with_result_expert_review_required(self):
        result = self.run_guard(VALID_EXPERT_REVIEW_RESULT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GÜLTIG", result.stdout)

    def test_missing_fields_are_rejected(self):
        result = self.run_guard(MISSING_FIELDS)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Reviewer", result.stderr)
        self.assertIn("Reviewer Agent Type", result.stderr)
        self.assertIn("Reviewer Agent ID", result.stderr)
        self.assertIn("Reviewed Commit", result.stderr)
        self.assertIn("Root Cause Addressed", result.stderr)
        self.assertIn("Regression Evidence Checked", result.stderr)
        self.assertIn("Guard Evidence Checked", result.stderr)
        self.assertIn("Scope Checked", result.stderr)
        self.assertIn("Remaining Risks", result.stderr)
        self.assertIn("Findings And Objections", result.stderr)

    def test_placeholder_field_value_is_rejected(self):
        result = self.run_guard(PLACEHOLDER_FIELD)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Remaining Risks", result.stderr)

    def test_invalid_result_value_is_rejected(self):
        result = self.run_guard(INVALID_RESULT_VALUE)
        self.assertEqual(result.returncode, 1)
        self.assertIn("ungültigen Wert", result.stderr)

    def test_finding_reference_to_nonexistent_finding_is_rejected(self):
        result = self.run_guard(UNKNOWN_FINDING_REFERENCE)
        self.assertEqual(result.returncode, 1)
        self.assertIn("P9-DOES-NOT-EXIST", result.stderr)

    def test_missing_reviewer_provenance_is_rejected(self):
        result = self.run_guard(MISSING_REVIEWER_PROVENANCE)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Reviewer Agent Type", result.stderr)
        self.assertIn("Reviewer Agent ID", result.stderr)

    def test_wrong_reviewer_agent_type_is_rejected(self):
        result = self.run_guard(WRONG_REVIEWER_AGENT_TYPE)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Reviewer Agent Type", result.stderr)
        self.assertIn("main-agent", result.stderr)


if __name__ == "__main__":
    unittest.main()
