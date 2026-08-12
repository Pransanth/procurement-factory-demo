"""Tests for validate-job-handler-scope.py.

Run with:
    python3 -m unittest factory.guards.test_validate_job_handler_scope

Like test_validate_finding.py, this invokes the guard as a subprocess
against temporary fixture files -- never against real files under
app/jobs/. The fixtures never need to actually import successfully (the
guard only parses their AST, it never executes them), so they can name
modules like app.jobs.handlers / app.repositories without those imports
having to resolve.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "validate-job-handler-scope.py"

NOT_A_HANDLER = """\
def helper(conn, organization_id):
    return conn, organization_id
"""

CLEAN_HANDLER = """\
from app.jobs.handlers import register

JOB_TYPE = "example_job"


def handle(scope, payload):
    return {"ok": True}


register(JOB_TYPE, handle)
"""

BAD_DIRECT_REPOSITORY_IMPORT = """\
from app.jobs.handlers import register
from app.repositories import procurement_requests

JOB_TYPE = "bad_import_job"


def handle(scope, payload):
    return procurement_requests.list_for_org(None, 1)


register(JOB_TYPE, handle)
"""

BAD_RAW_CONNECTION_PARAMETER = """\
from app.jobs.handlers import register

JOB_TYPE = "bad_conn_job"


def handle(conn, payload):
    return {"ok": True}


register(JOB_TYPE, handle)
"""

BAD_FREE_ORGANIZATION_ID_PARAMETER = """\
from app.jobs.handlers import register

JOB_TYPE = "bad_org_id_job"


def handle(scope, payload, organization_id):
    return {"organization_id": organization_id}


register(JOB_TYPE, handle)
"""

BAD_PRIVATE_SCOPE_ATTRIBUTE_ACCESS = """\
from app.jobs.handlers import register

JOB_TYPE = "bad_bypass_job"


def handle(scope, payload):
    conn = scope._conn
    return conn.execute("SELECT 1").fetchone()


register(JOB_TYPE, handle)
"""

BAD_MULTIPLE_VIOLATIONS = """\
from app.jobs.handlers import register
from app.repositories import audit_log

JOB_TYPE = "bad_everything_job"


def handle(conn, payload):
    return audit_log.list_for_org(scope._conn, 1)


register(JOB_TYPE, handle)
"""


class ValidateJobHandlerScopeTests(unittest.TestCase):
    def run_guard(self, content):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
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

    def test_non_handler_file_is_skipped(self):
        result = self.run_guard(NOT_A_HANDLER)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ÜBERSPRUNGEN", result.stdout)

    def test_clean_handler_passes(self):
        result = self.run_guard(CLEAN_HANDLER)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GÜLTIG", result.stdout)

    def test_direct_repository_import_is_rejected(self):
        result = self.run_guard(BAD_DIRECT_REPOSITORY_IMPORT)
        self.assertEqual(result.returncode, 1)
        self.assertIn("app.repositories", result.stderr)

    def test_raw_connection_parameter_is_rejected(self):
        result = self.run_guard(BAD_RAW_CONNECTION_PARAMETER)
        self.assertEqual(result.returncode, 1)
        self.assertIn("'conn'", result.stderr)

    def test_free_organization_id_parameter_is_rejected(self):
        result = self.run_guard(BAD_FREE_ORGANIZATION_ID_PARAMETER)
        self.assertEqual(result.returncode, 1)
        self.assertIn("'organization_id'", result.stderr)

    def test_private_scope_attribute_access_is_rejected(self):
        result = self.run_guard(BAD_PRIVATE_SCOPE_ATTRIBUTE_ACCESS)
        self.assertEqual(result.returncode, 1)
        self.assertIn("_conn", result.stderr)

    def test_multiple_violations_are_all_reported(self):
        result = self.run_guard(BAD_MULTIPLE_VIOLATIONS)
        self.assertEqual(result.returncode, 1)
        self.assertIn("app.repositories", result.stderr)
        self.assertIn("'conn'", result.stderr)
        self.assertIn("_conn", result.stderr)


if __name__ == "__main__":
    unittest.main()
