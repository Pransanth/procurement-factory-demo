"""Tests for the canonical factory check runner run-factory-checks.py.

Run with:
    python3 -m unittest factory.guards.test_run_factory_checks

These tests point the real runner at temporary findings/jobs/reviews
directories via --findings-dir / --jobs-dir / --reviews-dir, so the real
factory/findings/P1-DEMO-1.md, the real app/jobs/ files and the real
factory/reviews/ are never touched. Tests that only exercise one check
dimension pass empty directories for the others so each test stays
hermetic and isolated to the one check kind it is about. Review fixtures
reference "Finding: P1-DEMO-1" -- that finding genuinely exists in this
repo, so validate-review.py's existence cross-check passes; this is a
read-only check, never a mutation of the real finding.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "run-factory-checks.py"

VALID_OPEN_A = """\
# TEST-A

Status: OPEN

## Befund

Beispielbeschreibung A.

## Analyse

Root Cause: Not yet analyzed
Affected Components: Not yet analyzed
Relevant Architecture: Not yet analyzed
Recommended Repair: Not yet analyzed
Regression Test Plan: Not yet analyzed
Central Guard Plan: Not yet analyzed
Expected Blast Radius: Not yet analyzed
Risk Assessment: Not yet analyzed
"""

VALID_OPEN_B = VALID_OPEN_A.replace("TEST-A", "TEST-B").replace(
    "Beispielbeschreibung A.", "Beispielbeschreibung B."
)

INVALID_ANALYZED = """\
# TEST-BROKEN

Status: ANALYZED

## Befund

Beispielbeschreibung, unvollstaendig analysiert.

## Analyse

Root Cause: Not yet analyzed
"""

CLEAN_HANDLER = """\
from app.jobs.handlers import register

JOB_TYPE = "example_job"


def handle(scope, payload):
    return {"ok": True}


register(JOB_TYPE, handle)
"""

BAD_HANDLER = """\
from app.jobs.handlers import register
from app.repositories import procurement_requests

JOB_TYPE = "bad_job"


def handle(conn, payload):
    return procurement_requests.list_for_org(conn, 1)


register(JOB_TYPE, handle)
"""

VALID_REVIEW = """\
# P1-DEMO-1

Finding: P1-DEMO-1
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

BROKEN_REVIEW = """\
# P1-DEMO-1

Finding: P1-DEMO-1
Result: PASS
"""


class RunFactoryChecksTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="factory-runner-test-")
        self.findings_dir = Path(self.tmp_dir) / "findings"
        self.jobs_dir = Path(self.tmp_dir) / "jobs"
        self.reviews_dir = Path(self.tmp_dir) / "reviews"
        self.findings_dir.mkdir()
        self.jobs_dir.mkdir()
        self.reviews_dir.mkdir()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def write_finding(self, name, content):
        (self.findings_dir / name).write_text(content, encoding="utf-8")

    def write_job_file(self, name, content):
        (self.jobs_dir / name).write_text(content, encoding="utf-8")

    def write_review(self, name, content):
        (self.reviews_dir / name).write_text(content, encoding="utf-8")

    def run_runner(self):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--findings-dir",
                str(self.findings_dir),
                "--jobs-dir",
                str(self.jobs_dir),
                "--reviews-dir",
                str(self.reviews_dir),
            ],
            capture_output=True,
            text=True,
        )

    def test_all_valid_findings_pass(self):
        self.write_finding("a.md", VALID_OPEN_A)
        self.write_finding("b.md", VALID_OPEN_B)
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ALLE BESTANDEN", result.stdout)
        self.assertIn("[OK]", result.stdout)

    def test_single_invalid_finding_fails(self):
        self.write_finding("broken.md", INVALID_ANALYZED)
        result = self.run_runner()
        self.assertEqual(result.returncode, 1)
        self.assertIn("broken.md", result.stderr)
        self.assertIn("FEHLGESCHLAGEN", result.stderr)

    def test_mixed_findings_report_only_the_broken_one(self):
        self.write_finding("a.md", VALID_OPEN_A)
        self.write_finding("broken.md", INVALID_ANALYZED)
        result = self.run_runner()
        self.assertEqual(result.returncode, 1)
        combined = result.stdout + result.stderr
        self.assertIn("[OK]     finding-validator: a.md", combined)
        self.assertIn("[FEHLER] finding-validator: broken.md", combined)

    def test_no_findings_at_all_is_not_a_failure(self):
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ALLE BESTANDEN", result.stdout)

    def test_clean_job_handler_passes(self):
        self.write_job_file("example_job.py", CLEAN_HANDLER)
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[OK]     job-handler-guard: example_job.py", result.stdout)

    def test_unsafe_job_handler_fails(self):
        self.write_job_file("bad_job.py", BAD_HANDLER)
        result = self.run_runner()
        self.assertEqual(result.returncode, 1)
        self.assertIn("[FEHLER] job-handler-guard: bad_job.py", result.stderr)
        self.assertIn("FEHLGESCHLAGEN", result.stderr)

    def test_mixed_jobs_report_only_the_unsafe_one(self):
        self.write_job_file("example_job.py", CLEAN_HANDLER)
        self.write_job_file("bad_job.py", BAD_HANDLER)
        result = self.run_runner()
        self.assertEqual(result.returncode, 1)
        combined = result.stdout + result.stderr
        self.assertIn("[OK]     job-handler-guard: example_job.py", combined)
        self.assertIn("[FEHLER] job-handler-guard: bad_job.py", combined)

    def test_test_prefixed_job_files_are_not_checked(self):
        # test_*.py files are not production handler files; the runner must
        # not even ask the guard about them.
        self.write_job_file("test_example_job.py", BAD_HANDLER)
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("test_example_job.py", result.stdout + result.stderr)

    def test_invalid_finding_and_unsafe_job_are_both_reported(self):
        self.write_finding("broken.md", INVALID_ANALYZED)
        self.write_job_file("bad_job.py", BAD_HANDLER)
        result = self.run_runner()
        self.assertEqual(result.returncode, 1)
        combined = result.stdout + result.stderr
        self.assertIn("[FEHLER] finding-validator: broken.md", combined)
        self.assertIn("[FEHLER] job-handler-guard: bad_job.py", combined)

    def test_valid_review_passes(self):
        self.write_review("P1-DEMO-1.md", VALID_REVIEW)
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[OK]     review-guard: P1-DEMO-1.md", result.stdout)

    def test_broken_review_fails(self):
        self.write_review("P1-DEMO-1.md", BROKEN_REVIEW)
        result = self.run_runner()
        self.assertEqual(result.returncode, 1)
        self.assertIn("[FEHLER] review-guard: P1-DEMO-1.md", result.stderr)
        self.assertIn("FEHLGESCHLAGEN", result.stderr)

    def test_readme_in_reviews_dir_is_not_checked(self):
        # README.md documents the format; it is not a review artifact.
        self.write_review("README.md", BROKEN_REVIEW)
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("README.md", result.stdout + result.stderr)

    def test_no_reviews_at_all_is_not_a_failure(self):
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ALLE BESTANDEN", result.stdout)

    def test_ready_for_closure_finding_with_matching_pass_review_passes_end_to_end(self):
        # validate-review.py's "Finding" cross-check always resolves against
        # the REAL factory/findings/ (it has no knowledge of this test's
        # --findings-dir override), so this fixture deliberately keeps
        # "Finding: P1-DEMO-1", which genuinely exists there -- the
        # READY_FOR_CLOSURE finding under test is still the independent
        # TEST-CLOSURE fixture in the temporary --findings-dir below.
        review_path = self.reviews_dir / "TEST-CLOSURE.md"
        review_path.write_text(VALID_REVIEW, encoding="utf-8")

        finding = f"""\
# TEST-CLOSURE

Status: READY_FOR_CLOSURE

## Befund

Beispielbeschreibung.

## Analyse

Root Cause: Fehlende Pruefung der Organisation beim Erstellen neuer Jobs.
Affected Components: Job-Scheduler, Job-Worker.
Relevant Architecture: Hintergrundjobs laufen ohne zentralen Org-Filter.
Recommended Repair: Zentralen Guard einfuehren, der die Org-ID erzwingt.
Regression Test Plan: Neue Tests fuer Jobs mit falscher/fehlender Org-ID.
Central Guard Plan: Guard-Funktion, die jeder Job-Registrierung vorgeschaltet wird.
Expected Blast Radius: Nur neue Hintergrundjobs, keine bestehenden Endpunkte.
Risk Assessment: Gering, da rein additive Pruefung ohne bestehendes Verhalten zu aendern.
Verification Evidence: Alle relevanten Tests gruen.
CI Evidence: GitHub Actions Run #123 auf main, gruen.
Review Artifact: {review_path}
"""
        self.write_finding("TEST-CLOSURE.md", finding)
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ALLE BESTANDEN", result.stdout)


if __name__ == "__main__":
    unittest.main()
