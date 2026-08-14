"""Tests for the service-layer role-authorization guard (P1-DEMO-5).

Run with:
    python3 -m unittest factory.guards.test_validate_service_role_authorization

Every fixture is written to a temporary file, so the real files under
app/services/ are never touched. The two central fixtures are the
authorization check of app/services/user_admin_service.py exactly as it
read BEFORE the P1-DEMO-5 fix (must be rejected) and exactly as it reads
AFTER it (must be accepted) -- that pairing is what makes this guard's
claim checkable instead of asserted.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().parent / "validate-service-role-authorization.py"

UNFIXED_EXCLUSION_CHECK = '''\
def change_user_role(conn, organization_id, actor_user_id, target_user_id, new_role):
    actor = users.get_by_id(conn, organization_id, actor_user_id)
    if actor.role == "member":
        raise ValueError("not authorized")
    return users.update_role(conn, organization_id, target_user_id, new_role)
'''

FIXED_ALLOWLIST_CHECK = '''\
ROLE_ADMINISTERING_ROLES = ("admin",)


def change_user_role(conn, organization_id, actor_user_id, target_user_id, new_role):
    actor = users.get_by_id(conn, organization_id, actor_user_id)
    if actor.role not in ROLE_ADMINISTERING_ROLES:
        raise ValueError("not authorized")
    return users.update_role(conn, organization_id, target_user_id, new_role)
'''

INEQUALITY_EXCLUSION_CHECK = '''\
def decide(conn, actor):
    if actor.role != "admin":
        raise ValueError("not authorized")
    return True
'''

LITERAL_TUPLE_ALLOWLIST = '''\
def decide(conn, approver):
    if approver.role not in ("approver", "admin"):
        raise ValueError("not authorized")
    return True
'''

REVERSED_OPERAND_ORDER = '''\
def decide(conn, actor):
    if "member" == actor.role:
        raise ValueError("not authorized")
    return True
'''

PLAIN_ROLE_VARIABLE = '''\
def decide(conn, actor):
    role = actor.role
    if role == "member":
        raise ValueError("not authorized")
    return True
'''

ROLE_IN_A_STRING_ONLY = '''\
def decide(conn, actor):
    if actor.role not in ROLE_ADMINISTERING_ROLES:
        raise ValueError(f"user has role '{actor.role}' and may not administer roles")
    return True
'''

NO_ROLE_LOGIC_AT_ALL = '''\
from app.repositories import audit_log


def record(conn, organization_id, action):
    return audit_log.record(conn, organization_id, action=action)
'''

UNRELATED_STRING_COMPARISON = '''\
def submit(conn, request):
    if request.status != "draft":
        raise ValueError("cannot submit")
    return True
'''


class ValidateServiceRoleAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="role-auth-guard-test-")
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

    def test_unfixed_exclusion_check_is_rejected(self):
        result = self.run_guard(UNFIXED_EXCLUSION_CHECK)
        self.assertEqual(result.returncode, 1)
        self.assertIn("UNGÜLTIG", result.stderr)
        self.assertIn("actor.role == 'member'", result.stderr)

    def test_fixed_allowlist_check_is_accepted(self):
        result = self.run_guard(FIXED_ALLOWLIST_CHECK)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GÜLTIG", result.stdout)

    def test_inequality_against_a_single_role_is_rejected(self):
        # "!= 'admin'" is the same single-role decision, only inverted: it
        # grants every role that happens not to be named.
        result = self.run_guard(INEQUALITY_EXCLUSION_CHECK)
        self.assertEqual(result.returncode, 1)
        self.assertIn("actor.role != 'admin'", result.stderr)

    def test_membership_against_a_literal_tuple_is_accepted(self):
        result = self.run_guard(LITERAL_TUPLE_ALLOWLIST)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reversed_operand_order_is_rejected(self):
        result = self.run_guard(REVERSED_OPERAND_ORDER)
        self.assertEqual(result.returncode, 1)
        self.assertIn("actor.role", result.stderr)

    def test_role_compared_through_a_plain_variable_is_rejected(self):
        result = self.run_guard(PLAIN_ROLE_VARIABLE)
        self.assertEqual(result.returncode, 1)
        self.assertIn("role == 'member'", result.stderr)

    def test_role_mentioned_only_inside_a_message_is_accepted(self):
        # Reading actor.role for an error message is not a comparison and
        # must not be flagged -- the real fixed module does exactly this.
        result = self.run_guard(ROLE_IN_A_STRING_ONLY)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_file_without_role_logic_passes_trivially(self):
        result = self.run_guard(NO_ROLE_LOGIC_AT_ALL)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unrelated_string_comparison_is_not_flagged(self):
        # status != "draft" is a state check, not an authorization decision.
        result = self.run_guard(UNRELATED_STRING_COMPARISON)
        self.assertEqual(result.returncode, 0, result.stderr)

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
