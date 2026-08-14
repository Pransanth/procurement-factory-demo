#!/usr/bin/env bash
# Deterministically create a finding worktree pinned to the current
# origin/main tip.
#
# Why this script exists: EnterWorktree's "fresh" base-ref mode (the
# harness default) resolves "the default branch" via the locally cached
# refs/remotes/origin/HEAD symref. `git fetch origin` does NOT refresh
# that symref -- only an explicit `git remote set-head` does. If it has
# drifted (observed in this repo: it pointed at the old, already-merged
# refs/remotes/origin/fix/P1-DEMO-1 instead of refs/remotes/origin/main),
# a worktree created via that implicit resolution silently starts from
# whatever stale commit the symref happens to point at, not from the
# current origin/main tip. This script never consults that symref: it
# always fetches origin, resolves origin/main explicitly, creates the
# worktree directly from that ref, and verifies the worktree's HEAD
# against the SHA it resolved before the caller is told the worktree is
# usable.
#
# Usage:
#   factory/scripts/create-finding-worktree.sh resolve
#       Fetches origin and prints the current origin/main SHA. Run this
#       first and capture its output -- that is the expected base SHA for
#       the "create" step below.
#
#   factory/scripts/create-finding-worktree.sh create <expected-sha> <path> <branch>
#       Creates a new worktree at <path> on new branch <branch>, directly
#       from origin/main (never from the current local branch or any
#       other implicit default). Immediately verifies the new worktree's
#       HEAD equals <expected-sha>, before any other command runs in it.
#       On match: prints "WORKTREE_READY <path> <branch> <sha>" and exits
#       0 -- the worktree is safe to enter (e.g. via EnterWorktree with
#       `path: <path>`) and use.
#       On mismatch: removes the worktree immediately, prints
#       "AUTONOMY_BLOCKER: ..." to stderr, and exits 1. The worktree is
#       never left behind for use.
#
# Typical caller sequence:
#   SHA="$(factory/scripts/create-finding-worktree.sh resolve)"
#   factory/scripts/create-finding-worktree.sh create "$SHA" .claude/worktrees/P1-DEMO-4 fix/P1-DEMO-4
set -euo pipefail

SUBCOMMAND="${1:-}"

case "$SUBCOMMAND" in
  resolve)
    git fetch origin
    git rev-parse origin/main
    ;;
  create)
    if [ "$#" -ne 4 ]; then
      echo "usage: create-finding-worktree.sh create <expected-sha> <path> <branch>" >&2
      exit 2
    fi
    EXPECTED_SHA="$2"
    WT_PATH="$3"
    BRANCH="$4"

    git worktree add -b "$BRANCH" "$WT_PATH" origin/main

    ACTUAL_SHA="$(git -C "$WT_PATH" rev-parse HEAD)"

    if [ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]; then
      git worktree remove --force "$WT_PATH"
      echo "AUTONOMY_BLOCKER: worktree HEAD ($ACTUAL_SHA) does not match expected origin/main ($EXPECTED_SHA) -- worktree discarded, not entered, not used." >&2
      exit 1
    fi

    echo "WORKTREE_READY $WT_PATH $BRANCH $ACTUAL_SHA"
    ;;
  *)
    echo "usage: create-finding-worktree.sh {resolve|create <expected-sha> <path> <branch>}" >&2
    exit 2
    ;;
esac
