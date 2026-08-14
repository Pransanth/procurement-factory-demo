#!/usr/bin/env python3
"""Deterministic, LLM-free guard for hand-written SQL in the service layer.

Usage:
    python3 factory/guards/validate-service-sql-org-scope.py <path-to-file.py>

This is the SECOND, additional protection layer for the security boundary
described in factory/findings/P1-DEMO-4.md. The PRIMARY boundary is the
query itself: every statement a service module issues against a
tenant-owned table has to carry its own organization_id predicate, bound to
the caller's organization_id. This guard cannot create that boundary -- it
can only catch a statement that lacks it before it lands in the codebase.

Why the service layer specifically: app/repositories/*.py enforces tenant
isolation once per function, and every caller inherits it. app/services/
composes those repositories -- except app/services/reporting_service.py,
which by design issues its own SQL because reports need aggregation,
ranking and joins the repository layer deliberately does not expose (see
that module's docstring). That exception moves the isolation obligation
from a layer that enforces it structurally to individual, hand-written
query strings. P1-DEMO-4 is exactly what happens when one of them forgets:
the totals query filtered on organization_id, the line-item query next to
it did not, and a report for one tenant listed another tenant's line items.

What is checked, per SQL string literal passed to .execute(),
.executemany() or .executescript():
    1. Which tenant-owned tables the statement references, taken from its
       FROM / JOIN / UPDATE / INSERT INTO / DELETE FROM clauses, together
       with their aliases. Tenant-owned means: the table carries an
       organization_id column in app/db.py -- users, suppliers,
       procurement_requests, approvals, audit_log, audit_log_archive,
       jobs. The organizations table itself is not tenant-owned (it IS the
       tenant) and is ignored.
    2. For a read/update/delete statement, each referenced tenant-owned
       table must appear in an organization_id predicate:
           <alias>.organization_id = ?          (or a named parameter)
           <alias>.organization_id = <other>.organization_id
       For a statement that references exactly one table and gives it no
       alias, the unqualified form organization_id = ? is accepted too --
       it is unambiguous there.
    3. For INSERT INTO <tenant table>, the column list must name
       organization_id.

Deliberately NOT attempted (same posture as
factory/guards/validate-job-handler-scope.py): this guard reads only
statically visible string literals. SQL assembled at runtime -- f-strings,
concatenation of non-literals, a query built by a helper, getattr
indirection -- is not analyzed and is reported as skipped, not as safe. It
is a second layer over the actual boundary (the predicate in the query),
never a substitute for it.

Exit code 0: no violation found (including files with no raw SQL at all).
Exit code 1: at least one statement references a tenant-owned table
             without the required organization_id predicate; details are
             printed to stderr.
"""
import ast
import re
import sys
from pathlib import Path

# Tables carrying an organization_id column in app/db.py. "organizations"
# is deliberately absent: it is the tenant table itself, not tenant-owned.
TENANT_TABLES = {
    "users",
    "suppliers",
    "procurement_requests",
    "approvals",
    "audit_log",
    "audit_log_archive",
    "jobs",
}

SQL_EXECUTE_METHODS = {"execute", "executemany", "executescript"}

# Words that can follow a table name without being an alias.
SQL_KEYWORDS_AFTER_TABLE = {
    "on",
    "where",
    "set",
    "values",
    "using",
    "group",
    "order",
    "limit",
    "having",
    "union",
    "select",
    "join",
    "left",
    "right",
    "inner",
    "outer",
    "cross",
    "natural",
    "and",
    "or",
    "as",
    "returning",
}

TABLE_REF_RE = re.compile(
    r"\b(?:from|join|update|into)\s+([A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\s+(?:as\s+)?([A-Za-z_][A-Za-z0-9_]*))?",
    re.IGNORECASE,
)

INSERT_INTO_RE = re.compile(
    r"\binsert\s+into\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)", re.IGNORECASE
)

# Right-hand side of an accepted organization_id predicate: a positional
# parameter, a named parameter, or another table's organization_id column.
PREDICATE_RHS = r"(?:\?|:[A-Za-z_][A-Za-z0-9_]*|[A-Za-z_][A-Za-z0-9_]*\.organization_id)"


def normalize(sql):
    return " ".join(sql.split())


def find_table_references(sql):
    """Return a list of (table_name, alias_or_None) in statement order."""
    references = []
    for match in TABLE_REF_RE.finditer(sql):
        table = match.group(1)
        alias = match.group(2)
        if alias is not None and alias.lower() in SQL_KEYWORDS_AFTER_TABLE:
            alias = None
        references.append((table, alias))
    return references


def has_predicate_for(sql, qualifier):
    pattern = re.compile(
        r"\b" + re.escape(qualifier) + r"\.organization_id\s*=\s*" + PREDICATE_RHS,
        re.IGNORECASE,
    )
    return bool(pattern.search(sql))


def has_unqualified_predicate(sql):
    pattern = re.compile(
        r"(?<![A-Za-z0-9_.])organization_id\s*=\s*" + PREDICATE_RHS, re.IGNORECASE
    )
    return bool(pattern.search(sql))


def check_insert_statements(sql):
    """Return error strings for INSERTs into tenant tables lacking the column."""
    errors = []
    for match in INSERT_INTO_RE.finditer(sql):
        table = match.group(1)
        if table.lower() not in TENANT_TABLES:
            continue
        columns = [column.strip().lower() for column in match.group(2).split(",")]
        if "organization_id" not in columns:
            errors.append(
                f"INSERT INTO '{table}' fuehrt keine Spalte 'organization_id' -- ein Datensatz "
                "einer mandantengebundenen Tabelle muss seinen Mandanten explizit setzen."
            )
    return errors


def check_statement(sql):
    """Return a list of human-readable error strings for one SQL literal."""
    sql = normalize(sql)
    errors = check_insert_statements(sql)

    references = find_table_references(sql)
    is_insert_only = bool(re.match(r"^\s*insert\b", sql, re.IGNORECASE))
    if is_insert_only:
        return errors

    tenant_references = [
        (table, alias) for table, alias in references if table.lower() in TENANT_TABLES
    ]
    single_unaliased_table = len(references) == 1 and references[0][1] is None

    for table, alias in tenant_references:
        if alias and has_predicate_for(sql, alias):
            continue
        if has_predicate_for(sql, table):
            continue
        if single_unaliased_table and has_unqualified_predicate(sql):
            continue
        qualifier = alias or table
        errors.append(
            f"Tabelle '{table}' wird ohne organization_id-Praedikat gelesen -- erwartet wird "
            f"'{qualifier}.organization_id = ?' (oder die Gleichsetzung mit der organization_id "
            f"einer anderen referenzierten Tabelle). Statement: {sql}"
        )

    return errors


def iter_sql_literals(tree):
    """Yield (lineno, sql_text_or_None) for each .execute*()-style call.

    A yielded None means: the call's first argument is not a plain string
    literal, so this guard cannot analyze it statically.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in SQL_EXECUTE_METHODS:
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            yield node.lineno, first_arg.value
        else:
            yield node.lineno, None


def validate_service_file(path):
    """Return (statement_count, skipped_count, errors: list[str])."""
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))

    statement_count = 0
    skipped_count = 0
    errors = []

    for lineno, sql in iter_sql_literals(tree):
        if sql is None:
            skipped_count += 1
            continue
        statement_count += 1
        for error in check_statement(sql):
            errors.append(f"Zeile {lineno}: {error}")

    return statement_count, skipped_count, errors


def main(argv):
    if len(argv) != 2:
        print(
            "Usage: validate-service-sql-org-scope.py <path-to-file.py>",
            file=sys.stderr,
        )
        return 1

    path = Path(argv[1])
    if not path.is_file():
        print(f"Datei nicht gefunden: {path}", file=sys.stderr)
        return 1

    statement_count, skipped_count, errors = validate_service_file(path)

    if errors:
        print(f"UNGÜLTIG: {path}", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    if statement_count == 0 and skipped_count == 0:
        print(f"ÜBERSPRUNGEN: {path} (kein rohes SQL in dieser Datei)")
        return 0

    suffix = ""
    if skipped_count:
        suffix = (
            f", {skipped_count} nicht-literale SQL-Argument(e) nicht analysierbar "
            "(siehe Guard-Docstring)"
        )
    print(
        f"GÜLTIG: {path} ({statement_count} SQL-Statement(s) mit organization_id-Praedikat"
        f"{suffix})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
