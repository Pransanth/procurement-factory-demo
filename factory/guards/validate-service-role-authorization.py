#!/usr/bin/env python3
"""Deterministic, LLM-free AST guard for role checks in the service layer.

Usage:
    python3 factory/guards/validate-service-role-authorization.py <path-to-file.py>

This is the SECOND, additional protection layer for the security boundary
described in factory/findings/P1-DEMO-5.md. The PRIMARY boundary is the
check inside the service function: the acting user's role must be tested
against an explicit allowlist of roles permitted to perform the operation.
This guard cannot create that boundary -- it can only refuse the shape of
the defect the finding is made of.

The defect, precisely: change_user_role() decided authority by exclusion,
"if actor.role == 'member': raise". That names who may NOT act. Every role
nobody thought to name -- here 'approver', the middle role of
app/db.py's CHECK(role IN ('member', 'approver', 'admin')) -- silently
passed and could assign any role, including 'admin', including to itself.
An allowlist ("if actor.role not in ROLE_ADMINISTERING_ROLES: raise")
fails the other way: a role that is added later is unprivileged until
someone deliberately adds it. app/repositories/approvals.py:43 already
used that form for its own operation (finding P1-DEMO-3), so the two
authorization decisions in this codebase were written as each other's
logical inverse -- which is exactly what nothing detected.

What is checked, per Python file:
    Every comparison whose operator is == or != and where one side is a
    role value and the other a string literal, is rejected. A "role value"
    is an attribute access ending in .role (actor.role, user.role,
    self.actor.role) or a plain name role / actor_role / user_role.
    Membership tests -- "in" / "not in" against a constant, a module-level
    allowlist name, or a literal tuple/list/set -- are the sanctioned form
    and pass.

Deliberately NOT attempted (same posture as the other guards here):
    - This guard sees the syntactic FORM of an authorization decision, not
      its meaning. It cannot know whether the allowlist contains the right
      roles, whether it is rebound at runtime, or whether it is consulted
      at all: a service function with NO role check whatsoever is
      unremarkable to it. Only the boundary itself -- the check in the
      function -- provides the actual guarantee.
    - It does not follow values. A role compared through an intermediate
      variable with an unrecognized name, a dict lookup, or a helper
      function is not recognized as a role comparison. Concretely, two
      ways to write the same defect pass this guard: a comparison against
      a NAMED constant ("actor.role == MEMBER_ROLE") instead of a string
      literal, and an exclusion expressed as a membership test over a
      denylist ("if actor.role in DENIED_ROLES: raise"). Both are pinned
      as known-limitation fixtures in this guard's tests so the gap is
      recorded rather than implied.
    - It says nothing about which roles exist; app/db.py's CHECK
      constraint remains the authority on that.

Exit code 0: no exclusion-style role comparison found (including files
             with no role logic at all).
Exit code 1: at least one such comparison; details are printed to stderr.
"""
import ast
import sys
from pathlib import Path

ROLE_ATTRIBUTE = "role"
ROLE_NAMES = {"role", "actor_role", "user_role"}


def is_role_value(node):
    """True if `node` reads something this guard treats as a role value."""
    if isinstance(node, ast.Attribute) and node.attr == ROLE_ATTRIBUTE:
        return True
    if isinstance(node, ast.Name) and node.id in ROLE_NAMES:
        return True
    return False


def is_string_literal(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def describe(node):
    """Render a comparison operand for the error message."""
    if isinstance(node, ast.Attribute):
        return f"{describe(node.value)}.{node.attr}" if node.value else node.attr
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant):
        return repr(node.value)
    return "<Ausdruck>"


def check_comparison(node):
    """Return error strings for one Compare node."""
    errors = []
    left = node.left

    for operator, comparator in zip(node.ops, node.comparators):
        if not isinstance(operator, (ast.Eq, ast.NotEq)):
            left = comparator
            continue

        role_side = None
        literal_side = None
        if is_role_value(left) and is_string_literal(comparator):
            role_side, literal_side = left, comparator
        elif is_role_value(comparator) and is_string_literal(left):
            role_side, literal_side = comparator, left

        if role_side is not None:
            symbol = "==" if isinstance(operator, ast.Eq) else "!="
            errors.append(
                f"Zeile {node.lineno}: Rollenvergleich "
                f"'{describe(role_side)} {symbol} {describe(literal_side)}' -- eine "
                "Autorisierungsentscheidung darf nicht eine einzelne Rolle benennen "
                "(Ausschluss bzw. Einzelfall), sondern muss gegen eine explizite Allowlist "
                "pruefen: 'not in ROLE_...' bzw. 'in ROLE_...'. Siehe "
                "factory/findings/P1-DEMO-5.md."
            )

        left = comparator

    return errors


def validate_service_file(path):
    """Return a list of human-readable error strings; empty means valid."""
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))

    errors = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            errors.extend(check_comparison(node))
    return errors


def main(argv):
    if len(argv) != 2:
        print(
            "Usage: validate-service-role-authorization.py <path-to-file.py>",
            file=sys.stderr,
        )
        return 1

    path = Path(argv[1])
    if not path.is_file():
        print(f"Datei nicht gefunden: {path}", file=sys.stderr)
        return 1

    errors = validate_service_file(path)

    if errors:
        print(f"UNGÜLTIG: {path}", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"GÜLTIG: {path} (keine Rollenpruefung per Gleichheitsvergleich)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
