#!/usr/bin/env bash
# Canonical, narrowly-scoped read-only GitHub/CI query helper for routine
# factory automation. Wraps factory/scripts/gh-api.sh with fixed
# subcommands so routine checks (PR status, check-runs, Actions runs/jobs,
# ruleset/required-status-check status, repo metadata) never need an ad hoc
# `| python3 -c "..."` pipeline -- each subcommand is a single, statically
# recognizable command shape with only plain-data arguments (PR number,
# commit SHA, branch name, run id). No token is ever printed; the
# credential-helper's benign "failed to store" keychain-write noise (see
# gh-api.sh) is suppressed here so callers get clean JSON on stdout.
#
# Usage:
#   factory/scripts/gh-query.sh repo
#   factory/scripts/gh-query.sh pr <NUMBER>
#   factory/scripts/gh-query.sh check-runs <SHA>
#   factory/scripts/gh-query.sh actions-run <BRANCH>
#   factory/scripts/gh-query.sh actions-jobs <RUN_ID>
#   factory/scripts/gh-query.sh branch-rules <BRANCH>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GH_API="$SCRIPT_DIR/gh-api.sh"

if [ "$#" -lt 1 ]; then
  echo "usage: gh-query.sh {repo|pr|check-runs|actions-run|actions-jobs|branch-rules} [arg]" >&2
  exit 2
fi

SUBCOMMAND="$1"
ARG="${2:-}"

case "$SUBCOMMAND" in
  repo)
    "$GH_API" GET "" 2>/dev/null
    ;;
  pr)
    [ -n "$ARG" ] || { echo "usage: gh-query.sh pr <NUMBER>" >&2; exit 2; }
    "$GH_API" GET "/pulls/$ARG" 2>/dev/null
    ;;
  check-runs)
    [ -n "$ARG" ] || { echo "usage: gh-query.sh check-runs <SHA>" >&2; exit 2; }
    "$GH_API" GET "/commits/$ARG/check-runs" 2>/dev/null
    ;;
  actions-run)
    [ -n "$ARG" ] || { echo "usage: gh-query.sh actions-run <BRANCH>" >&2; exit 2; }
    "$GH_API" GET "/actions/runs?branch=$ARG" 2>/dev/null
    ;;
  actions-jobs)
    [ -n "$ARG" ] || { echo "usage: gh-query.sh actions-jobs <RUN_ID>" >&2; exit 2; }
    "$GH_API" GET "/actions/runs/$ARG/jobs" 2>/dev/null
    ;;
  branch-rules)
    [ -n "$ARG" ] || { echo "usage: gh-query.sh branch-rules <BRANCH>" >&2; exit 2; }
    "$GH_API" GET "/rules/branches/$ARG" 2>/dev/null
    ;;
  *)
    echo "ERROR: unknown subcommand '$SUBCOMMAND'" >&2
    exit 2
    ;;
esac
