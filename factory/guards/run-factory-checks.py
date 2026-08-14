#!/usr/bin/env python3
"""Canonical entry point for all factory checks.

This is the ONE command that decides whether the current repository state
passes the factory's automated checks. Everything else -- the local Stop
hook, GitHub CI -- is expected to call this script rather than
re-implement its own checking logic.

There are four kinds of check, run in order:
  1. Every finding under factory/findings/ must pass
     factory/guards/validate-finding.py. For a finding trying to reach
     READY_FOR_CLOSURE/CLOSED, this already includes checking that its
     referenced review artifact exists and says "Result: PASS" -- see that
     script's docstring.
  2. Every file under app/jobs/ must pass
     factory/guards/validate-job-handler-scope.py (a file that is not a
     job handler passes trivially -- see that script's docstring for what
     counts as a handler).
  3. Every review artifact under factory/reviews/ must pass
     factory/guards/validate-review.py -- structural completeness only
     (are all required fields filled in, is Result a valid value). Whether
     a review's content is actually correct is not something a
     deterministic script can judge; that is the independent reviewer's
     job (.claude/agents/finding-closure-reviewer.md).
  4. Every file under app/services/ must pass
     factory/guards/validate-service-sql-org-scope.py -- an AST guard
     that requires every hand-written SQL statement in the service layer
     to carry an organization_id predicate for each tenant-owned table it
     touches (see factory/findings/P1-DEMO-4.md). A service file without
     raw SQL passes trivially.
More kinds can be added later; they would all be run from here, in one
place, so no caller ever has to duplicate checking logic.

No LLM calls, no network access, no external services -- everything here is
plain, deterministic Python standard library.

Usage:
    python3 factory/guards/run-factory-checks.py [--findings-dir PATH] [--jobs-dir PATH] [--reviews-dir PATH] [--services-dir PATH]

Exit code 0: every check passed (including the trivial case of nothing to
             check).
Exit code 1: at least one check failed. A summary of which check and which
             file failed is printed to stderr.
"""
import argparse
import subprocess
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
VALIDATOR = THIS_DIR / "validate-finding.py"
JOB_HANDLER_GUARD = THIS_DIR / "validate-job-handler-scope.py"
REVIEW_GUARD = THIS_DIR / "validate-review.py"
SERVICE_SQL_GUARD = THIS_DIR / "validate-service-sql-org-scope.py"
DEFAULT_FINDINGS_DIR = THIS_DIR.parent / "findings"
DEFAULT_JOBS_DIR = THIS_DIR.parent.parent / "app" / "jobs"
DEFAULT_REVIEWS_DIR = THIS_DIR.parent / "reviews"
DEFAULT_SERVICES_DIR = THIS_DIR.parent.parent / "app" / "services"


def run_finding_checks(findings_dir):
    """Run the finding validator against every finding in findings_dir.

    Returns (ok: bool, report_lines: list[str]).
    """
    report = []

    if not VALIDATOR.is_file():
        report.append(f"[FEHLER] Validator nicht gefunden: {VALIDATOR}")
        return False, report

    if not findings_dir.is_dir():
        report.append(f"Kein Findings-Verzeichnis unter {findings_dir} -- nichts zu pruefen.")
        return True, report

    finding_files = sorted(findings_dir.glob("*.md"))
    if not finding_files:
        report.append(f"Keine Findings unter {findings_dir} -- nichts zu pruefen.")
        return True, report

    ok = True
    for finding_file in finding_files:
        result = subprocess.run(
            [sys.executable, str(VALIDATOR), str(finding_file)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            report.append(f"[OK]     finding-validator: {finding_file.name}")
        else:
            ok = False
            report.append(f"[FEHLER] finding-validator: {finding_file.name}")
            for stream in (result.stdout, result.stderr):
                for line in stream.splitlines():
                    if line.strip():
                        report.append(f"           {line}")

    return ok, report


def run_job_handler_checks(jobs_dir):
    """Run the job-handler-scope guard against every *.py file in jobs_dir
    (test_*.py files are excluded -- the guard is only meaningful for
    production code, and its own tests use temporary fixture files, never
    real files under app/jobs/).

    Returns (ok: bool, report_lines: list[str]).
    """
    report = []

    if not JOB_HANDLER_GUARD.is_file():
        report.append(f"[FEHLER] Job-Handler-Guard nicht gefunden: {JOB_HANDLER_GUARD}")
        return False, report

    if not jobs_dir.is_dir():
        report.append(f"Kein Jobs-Verzeichnis unter {jobs_dir} -- nichts zu pruefen.")
        return True, report

    candidate_files = sorted(p for p in jobs_dir.glob("*.py") if not p.name.startswith("test_"))
    if not candidate_files:
        report.append(f"Keine Python-Dateien unter {jobs_dir} -- nichts zu pruefen.")
        return True, report

    ok = True
    for candidate_file in candidate_files:
        result = subprocess.run(
            [sys.executable, str(JOB_HANDLER_GUARD), str(candidate_file)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            suffix = " (kein Handler, uebersprungen)" if "ÜBERSPRUNGEN" in result.stdout else ""
            report.append(f"[OK]     job-handler-guard: {candidate_file.name}{suffix}")
        else:
            ok = False
            report.append(f"[FEHLER] job-handler-guard: {candidate_file.name}")
            for stream in (result.stdout, result.stderr):
                for line in stream.splitlines():
                    if line.strip():
                        report.append(f"           {line}")

    return ok, report


def run_review_checks(reviews_dir):
    """Run the review-artifact guard against every review file in reviews_dir
    (README.md is excluded -- it documents the format, it is not a review
    artifact itself).

    Returns (ok: bool, report_lines: list[str]).
    """
    report = []

    if not REVIEW_GUARD.is_file():
        report.append(f"[FEHLER] Review-Guard nicht gefunden: {REVIEW_GUARD}")
        return False, report

    if not reviews_dir.is_dir():
        report.append(f"Kein Reviews-Verzeichnis unter {reviews_dir} -- nichts zu pruefen.")
        return True, report

    candidate_files = sorted(p for p in reviews_dir.glob("*.md") if p.name != "README.md")
    if not candidate_files:
        report.append(f"Keine Review-Artefakte unter {reviews_dir} -- nichts zu pruefen.")
        return True, report

    ok = True
    for candidate_file in candidate_files:
        result = subprocess.run(
            [sys.executable, str(REVIEW_GUARD), str(candidate_file)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            report.append(f"[OK]     review-guard: {candidate_file.name}")
        else:
            ok = False
            report.append(f"[FEHLER] review-guard: {candidate_file.name}")
            for stream in (result.stdout, result.stderr):
                for line in stream.splitlines():
                    if line.strip():
                        report.append(f"           {line}")

    return ok, report


def run_service_sql_checks(services_dir):
    """Run the service-layer SQL org-scope guard against every *.py file in
    services_dir (test_*.py files are excluded -- the guard is only
    meaningful for production code, and its own tests use temporary
    fixture files, never real files under app/services/).

    The "is there anything to check at all?" question is deliberately
    answered BEFORE "does the guard script exist?": a project tree without
    an app/services/ directory (e.g. the throwaway fixture projects in
    .claude/hooks/test_stop_validate_findings.py) has no service-layer SQL
    that could be unscoped, so demanding the guard script there would fail
    a check that has nothing to check. Wherever service files DO exist, a
    missing guard script is still a hard failure -- the check is never
    silently skipped for real code.

    Returns (ok: bool, report_lines: list[str]).
    """
    report = []

    if not services_dir.is_dir():
        report.append(f"Kein Services-Verzeichnis unter {services_dir} -- nichts zu pruefen.")
        return True, report

    if not SERVICE_SQL_GUARD.is_file():
        report.append(f"[FEHLER] Service-SQL-Guard nicht gefunden: {SERVICE_SQL_GUARD}")
        return False, report

    candidate_files = sorted(p for p in services_dir.glob("*.py") if not p.name.startswith("test_"))
    if not candidate_files:
        report.append(f"Keine Python-Dateien unter {services_dir} -- nichts zu pruefen.")
        return True, report

    ok = True
    for candidate_file in candidate_files:
        result = subprocess.run(
            [sys.executable, str(SERVICE_SQL_GUARD), str(candidate_file)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            suffix = " (kein rohes SQL, uebersprungen)" if "ÜBERSPRUNGEN" in result.stdout else ""
            report.append(f"[OK]     service-sql-guard: {candidate_file.name}{suffix}")
        else:
            ok = False
            report.append(f"[FEHLER] service-sql-guard: {candidate_file.name}")
            for stream in (result.stdout, result.stderr):
                for line in stream.splitlines():
                    if line.strip():
                        report.append(f"           {line}")

    return ok, report


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--findings-dir",
        type=Path,
        default=DEFAULT_FINDINGS_DIR,
        help="Verzeichnis mit Finding-Dateien (Standard: factory/findings)",
    )
    parser.add_argument(
        "--jobs-dir",
        type=Path,
        default=DEFAULT_JOBS_DIR,
        help="Verzeichnis mit Background-Job-Dateien (Standard: app/jobs)",
    )
    parser.add_argument(
        "--reviews-dir",
        type=Path,
        default=DEFAULT_REVIEWS_DIR,
        help="Verzeichnis mit Review-Artefakten (Standard: factory/reviews)",
    )
    parser.add_argument(
        "--services-dir",
        type=Path,
        default=DEFAULT_SERVICES_DIR,
        help="Verzeichnis mit Service-Modulen (Standard: app/services)",
    )
    args = parser.parse_args(argv[1:])

    finding_ok, finding_report = run_finding_checks(args.findings_dir)
    jobs_ok, jobs_report = run_job_handler_checks(args.jobs_dir)
    reviews_ok, reviews_report = run_review_checks(args.reviews_dir)
    services_ok, services_report = run_service_sql_checks(args.services_dir)

    ok = finding_ok and jobs_ok and reviews_ok and services_ok
    report = finding_report + jobs_report + reviews_report + services_report

    stream = sys.stdout if ok else sys.stderr
    for line in report:
        print(line, file=stream)

    if ok:
        print("Factory-Checks: ALLE BESTANDEN", file=sys.stdout)
        return 0

    print("Factory-Checks: FEHLGESCHLAGEN", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
