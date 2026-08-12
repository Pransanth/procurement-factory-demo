#!/usr/bin/env python3
"""Deterministic, LLM-free AST guard for background job handler files.

Usage:
    python3 factory/guards/validate-job-handler-scope.py <path-to-file.py>

This is the SECOND, additional protection layer for the security boundary
described in factory/findings/P1-DEMO-1.md. The PRIMARY boundary is the
runtime one: app/jobs/scoped_repositories.py's ScopedRepositories, built
centrally by app/jobs/queue.py:run_pending and permanently bound to the
job's own organization_id, so a handler has no parameter through which it
could name a different organization. This guard cannot create that
boundary -- it can only catch a *deliberate* attempt to bypass it before
it lands in the codebase.

What counts as a "production handler file":
    A file whose module body contains a top-level call to `register(...)`
    -- the same call app/jobs/handlers.py:register() is meant to be used
    with. That is precisely what makes app/jobs/approval_reminder.py and
    app/jobs/audit_log_archival.py "handlers" today: this is a structural
    fact about the file (it registers a job_type), not a filename
    convention, so no separate list of handler filenames has to be kept in
    sync as new handlers are added.

    A file that does NOT contain such a call -- app/jobs/queue.py,
    app/jobs/handlers.py, app/jobs/scoped_repositories.py, any
    app/jobs/test_*.py file -- is not a handler, and this guard passes it
    trivially: there is nothing to check. In particular,
    ScopedRepositories' own implementation module legitimately imports
    app.repositories and legitimately defines `_conn`; it must never be
    flagged, and it is not, because it never calls register().

Checks performed on a file that IS a production handler:
    1. Direct imports of app.repositories (or any app.repositories.*
       submodule). Handlers are meant to reach org-scoped data only
       through the bound ScopedRepositories facade, never by importing
       the repository modules directly.
    2. The function registered via register(job_type, <this>) is
       inspected for parameters literally named "conn", "connection",
       "organization_id", or "org_id". The sanctioned signature is
       exactly handle(scope, payload); a parameter with one of these
       names reintroduces a raw connection or a freely choosable
       organization_id.
    3. Any attribute access named "_conn" anywhere in the file -- the one
       private attribute ScopedRepositories stores its bound connection
       under (app/jobs/scoped_repositories.py). Reaching for it from
       handler code is a deliberate bypass of the facade.

Deliberately NOT attempted (see factory/build-orders/P1-DEMO-1.md,
"Central Guard Evidence", for the full reasoning): tracking data flow,
detecting indirection (importlib, getattr on a module object, string-built
imports), or understanding dynamic attribute access. This guard is a
second, additional layer on top of the runtime boundary, not a substitute
for it -- a determined, deliberate bypass is still possible in Python's
dynamic type system.

Exit code 0: the file is not a production handler, or is one and passed
             every check.
Exit code 1: the file is a production handler and failed at least one
             check; details are printed to stderr.
"""
import ast
import sys
from pathlib import Path

BLOCKED_PARAMETER_NAMES = {"conn", "connection", "organization_id", "org_id"}
BLOCKED_PRIVATE_ATTRIBUTE = "_conn"
TENANT_REPOSITORY_MODULE = "app.repositories"


def _is_register_call(node):
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "register"
    if isinstance(func, ast.Attribute):
        return func.attr == "register"
    return False


def find_module_level_register_call(tree):
    """Return the top-level `register(...)` Call node, or None if this file
    never registers a handler (i.e. is not a production handler file)."""
    for node in tree.body:
        if isinstance(node, ast.Expr) and _is_register_call(node.value):
            return node.value
    return None


def find_function_def(tree, name):
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def check_tenant_repository_imports(tree):
    errors = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == TENANT_REPOSITORY_MODULE or module.startswith(TENANT_REPOSITORY_MODULE + "."):
                errors.append(
                    f"Zeile {node.lineno}: direkter Import von '{module}' -- Handler dürfen "
                    "org-gescopte Repositories nur über das gebundene ScopedRepositories-Objekt "
                    "erreichen, nicht direkt importieren."
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == TENANT_REPOSITORY_MODULE or alias.name.startswith(TENANT_REPOSITORY_MODULE + "."):
                    errors.append(
                        f"Zeile {node.lineno}: direkter Import von '{alias.name}' -- Handler dürfen "
                        "org-gescopte Repositories nur über das gebundene ScopedRepositories-Objekt "
                        "erreichen, nicht direkt importieren."
                    )
    return errors


def check_handler_signature(tree, register_call):
    errors = []
    if len(register_call.args) < 2:
        return errors  # not the register(job_type, handler) shape; nothing to check here

    handler_ref = register_call.args[1]
    if not isinstance(handler_ref, ast.Name):
        return errors  # handler passed as something other than a plain module-level name

    handler_def = find_function_def(tree, handler_ref.id)
    if handler_def is None:
        return errors

    param_names = {arg.arg for arg in handler_def.args.args}
    for name in sorted(param_names & BLOCKED_PARAMETER_NAMES):
        errors.append(
            f"Zeile {handler_def.lineno}: Handler-Funktion '{handler_def.name}' hat einen Parameter "
            f"namens '{name}' -- das sanktionierte API ist handle(scope, payload); ein Parameter mit "
            "diesem Namen deutet auf eine rohe Connection oder eine frei wählbare organization_id hin."
        )
    return errors


def check_private_scope_attribute_access(tree):
    errors = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == BLOCKED_PRIVATE_ATTRIBUTE:
            errors.append(
                f"Zeile {node.lineno}: Zugriff auf '{BLOCKED_PRIVATE_ATTRIBUTE}' -- das ist das "
                "private Interna von ScopedRepositories (app/jobs/scoped_repositories.py); "
                "Handler-Code darf nicht darauf zugreifen."
            )
    return errors


def validate_handler_file(path):
    """Return (is_handler: bool, errors: list[str])."""
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))

    register_call = find_module_level_register_call(tree)
    if register_call is None:
        return False, []

    errors = []
    errors.extend(check_tenant_repository_imports(tree))
    errors.extend(check_handler_signature(tree, register_call))
    errors.extend(check_private_scope_attribute_access(tree))
    return True, errors


def main(argv):
    if len(argv) != 2:
        print("Usage: validate-job-handler-scope.py <path-to-file.py>", file=sys.stderr)
        return 1

    path = Path(argv[1])
    if not path.is_file():
        print(f"Datei nicht gefunden: {path}", file=sys.stderr)
        return 1

    is_handler, errors = validate_handler_file(path)

    if not is_handler:
        print(f"ÜBERSPRUNGEN: {path} (kein Job-Handler -- kein Aufruf von register() auf Modulebene)")
        return 0

    if errors:
        print(f"UNGÜLTIG: {path}", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"GÜLTIG: {path} (Job-Handler, keine Umgehung der ScopedRepositories-Grenze erkannt)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
