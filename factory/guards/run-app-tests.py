#!/usr/bin/env python3
"""Canonical entry point for the application test suite (app/**/test_*.py).

The app/ package tree has no __init__.py files, so `unittest discover`
cannot reliably recurse into its subpackages (behavior varies by Python
version and invocation directory). This script instead finds every
app/**/test_*.py file itself and loads each as an explicit dotted module
name -- the same approach already used manually when this suite was last
verified for P1-DEMO-1 (factory/findings/P1-DEMO-1.md, Verification
Evidence) -- so the app test suite runs the same way locally and in CI.

Usage:
    python3 factory/guards/run-app-tests.py

Exit code 0: all app tests passed (including the trivial case of zero
             test files found).
Exit code 1: at least one app test failed or errored.
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
APP_DIR = REPO_ROOT / "app"


def discover_test_modules():
    modules = []
    for path in sorted(APP_DIR.rglob("test_*.py")):
        rel = path.relative_to(REPO_ROOT).with_suffix("")
        modules.append(".".join(rel.parts))
    return modules


def main():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    modules = discover_test_modules()
    if not modules:
        print(f"Keine app-Tests unter {APP_DIR} gefunden -- nichts zu pruefen.")
        return 0

    suite = unittest.TestLoader().loadTestsFromNames(modules)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
