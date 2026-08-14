"""Tests for the service-layer SQL org-scope guard (P1-DEMO-4).

Run with:
    python3 -m unittest factory.guards.test_validate_service_sql_org_scope

Every fixture is written to a temporary file, so the real files under
app/services/ are never touched by these tests. The two central fixtures
are the line-item query of app/services/reporting_service.py exactly as it
read BEFORE the P1-DEMO-4 fix (must be rejected) and exactly as it reads
AFTER it (must be accepted) -- that pairing is what makes this guard's
claim ("it detects the pattern the finding describes") checkable instead
of asserted.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().parent / "validate-service-sql-org-scope.py"

UNFIXED_REPORTING_QUERY = '''\
def monthly_spend_report(conn, organization_id, month, top_line_item_limit=5):
    month_prefix = f"{month}-%"
    line_item_rows = conn.execute(
        "SELECT pr.id AS request_id, pr.description AS description, "
        "pr.amount_cents AS amount_cents, pr.currency AS currency, "
        "s.name AS supplier_name "
        "FROM procurement_requests pr "
        "JOIN suppliers s ON s.id = pr.supplier_id "
        "WHERE pr.status = 'approved' AND pr.created_at LIKE ? "
        "ORDER BY pr.amount_cents DESC, pr.id ASC "
        "LIMIT ?",
        (month_prefix, top_line_item_limit),
    ).fetchall()
    return line_item_rows
'''

FIXED_REPORTING_QUERY = '''\
def monthly_spend_report(conn, organization_id, month, top_line_item_limit=5):
    month_prefix = f"{month}-%"
    line_item_rows = conn.execute(
        "SELECT pr.id AS request_id, pr.description AS description, "
        "pr.amount_cents AS amount_cents, pr.currency AS currency, "
        "s.name AS supplier_name "
        "FROM procurement_requests pr "
        "JOIN suppliers s ON s.id = pr.supplier_id "
        "AND s.organization_id = pr.organization_id "
        "WHERE pr.organization_id = ? AND pr.status = 'approved' AND pr.created_at LIKE ? "
        "ORDER BY pr.amount_cents DESC, pr.id ASC "
        "LIMIT ?",
        (organization_id, month_prefix, top_line_item_limit),
    ).fetchall()
    return line_item_rows
'''

SINGLE_TABLE_SCOPED = '''\
def totals(conn, organization_id, month_prefix):
    return conn.execute(
        "SELECT COUNT(*) AS approved_count FROM procurement_requests "
        "WHERE organization_id = ? AND status = 'approved' AND created_at LIKE ?",
        (organization_id, month_prefix),
    ).fetchone()
'''

SINGLE_TABLE_UNSCOPED = '''\
def totals(conn, month_prefix):
    return conn.execute(
        "SELECT COUNT(*) AS approved_count FROM procurement_requests "
        "WHERE status = 'approved' AND created_at LIKE ?",
        (month_prefix,),
    ).fetchone()
'''

NAMED_PARAMETER_SCOPED = '''\
def totals(conn, params):
    return conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE organization_id = :org_id",
        params,
    ).fetchone()
'''

NON_TENANT_TABLE = '''\
def all_organizations(conn):
    return conn.execute("SELECT * FROM organizations ORDER BY id").fetchall()
'''

NO_SQL_AT_ALL = '''\
from app.repositories import audit_log


def record(conn, organization_id, action):
    return audit_log.record(conn, organization_id, action=action)
'''

INSERT_WITHOUT_ORG_COLUMN = '''\
def add_supplier(conn, name):
    return conn.execute(
        "INSERT INTO suppliers (name, created_at) VALUES (?, ?)",
        (name, "2026-03-01T00:00:00+00:00"),
    )
'''

INSERT_WITH_ORG_COLUMN = '''\
def add_supplier(conn, organization_id, name):
    return conn.execute(
        "INSERT INTO suppliers (organization_id, name, created_at) VALUES (?, ?, ?)",
        (organization_id, name, "2026-03-01T00:00:00+00:00"),
    )
'''

DYNAMIC_SQL = '''\
def report(conn, organization_id, column):
    query = "SELECT " + column + " FROM procurement_requests WHERE organization_id = ?"
    return conn.execute(query, (organization_id,)).fetchall()
'''

UPDATE_UNSCOPED = '''\
def touch(conn, request_id, now):
    return conn.execute(
        "UPDATE procurement_requests SET updated_at = ? WHERE id = ?",
        (now, request_id),
    )
'''


class ValidateServiceSqlOrgScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="service-sql-guard-test-")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def run_guard(self, source, name="some_service.py"):
        path = Path(self.tmp_dir) / name
        path.write_text(source, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(GUARD), str(path)], capture_output=True, text=True
        )

    def test_unfixed_reporting_query_is_rejected(self):
        result = self.run_guard(UNFIXED_REPORTING_QUERY)
        self.assertEqual(result.returncode, 1)
        self.assertIn("UNGÜLTIG", result.stderr)
        self.assertIn("procurement_requests", result.stderr)
        self.assertIn("suppliers", result.stderr)

    def test_fixed_reporting_query_is_accepted(self):
        result = self.run_guard(FIXED_REPORTING_QUERY)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GÜLTIG", result.stdout)

    def test_single_unaliased_table_with_bare_predicate_is_accepted(self):
        result = self.run_guard(SINGLE_TABLE_SCOPED)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_single_unaliased_table_without_predicate_is_rejected(self):
        result = self.run_guard(SINGLE_TABLE_UNSCOPED)
        self.assertEqual(result.returncode, 1)
        self.assertIn("procurement_requests", result.stderr)

    def test_named_parameter_predicate_is_accepted(self):
        result = self.run_guard(NAMED_PARAMETER_SCOPED)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_non_tenant_table_needs_no_predicate(self):
        result = self.run_guard(NON_TENANT_TABLE)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_file_without_any_sql_passes_trivially(self):
        result = self.run_guard(NO_SQL_AT_ALL)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ÜBERSPRUNGEN", result.stdout)

    def test_insert_without_organization_id_column_is_rejected(self):
        result = self.run_guard(INSERT_WITHOUT_ORG_COLUMN)
        self.assertEqual(result.returncode, 1)
        self.assertIn("organization_id", result.stderr)

    def test_insert_with_organization_id_column_is_accepted(self):
        result = self.run_guard(INSERT_WITH_ORG_COLUMN)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_update_without_predicate_is_rejected(self):
        result = self.run_guard(UPDATE_UNSCOPED)
        self.assertEqual(result.returncode, 1)
        self.assertIn("procurement_requests", result.stderr)

    def test_dynamically_built_sql_is_reported_as_not_analyzable(self):
        # The guard must not claim a statement it cannot read is safe: it
        # exits 0 (nothing detected) but says so explicitly in its output.
        result = self.run_guard(DYNAMIC_SQL)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nicht analysierbar", result.stdout)

    def test_missing_file_is_an_error(self):
        result = subprocess.run(
            [sys.executable, str(GUARD), str(Path(self.tmp_dir) / "nope.py")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Datei nicht gefunden", result.stderr)


if __name__ == "__main__":
    unittest.main()
