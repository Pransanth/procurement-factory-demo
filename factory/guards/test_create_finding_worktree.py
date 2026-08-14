"""Regression test for factory/scripts/create-finding-worktree.sh.

Run with:
    python3 -m unittest factory.guards.test_create_finding_worktree

Reproduces, with a disposable local "remote", the exact failure observed in
a real multi-P1 run: a clone's cached refs/remotes/origin/HEAD symref had
drifted to point at an old, already-merged feature branch instead of
refs/remotes/origin/main. `git fetch origin` does not repair that symref,
so any mechanism that resolves "the default branch" through it (as
EnterWorktree's "fresh" base-ref mode does) can silently create a new
finding worktree from a stale commit instead of the current origin/main
tip.

This test builds a bare "remote", clones it, deliberately points the
clone's origin/HEAD at a stale branch (reproducing the drift), advances
the remote's real main further, and then asserts that
create-finding-worktree.sh's `resolve` step still returns the current
origin/main tip -- not the stale branch's commit -- and that `create`
produces a worktree pinned to exactly that SHA. It also asserts the
mismatch path: `create` given a deliberately wrong expected SHA discards
the worktree and reports AUTONOMY_BLOCKER instead of leaving anything
behind to work in.

A second failure from the same run is covered here as well: creating a
branch off a remote-tracking ref makes git set up upstream tracking by
default, which writes branch.<name>.remote/.merge into .git/config -- a
path this repo's sandbox deliberately refuses to write, so the branch
creation died with "could not lock config file .git/config: Operation not
permitted". The tests below pin that down without depending on the sandbox
being active: with a stale local branch and a drifted origin/HEAD present,
branch and worktree creation must leave .git/config byte-for-byte
unchanged while still being based on the current origin/main tip -- and a
negative control shows that dropping --no-track brings the .git/config
write straight back.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "create-finding-worktree.sh"

GIT_ENV_OVERRIDES = {
    "GIT_AUTHOR_NAME": "Factory Test",
    "GIT_AUTHOR_EMAIL": "factory-test@example.invalid",
    "GIT_COMMITTER_NAME": "Factory Test",
    "GIT_COMMITTER_EMAIL": "factory-test@example.invalid",
}


def _run_git(cwd, *args):
    """Run git in cwd and return the CompletedProcess, success or not."""
    env = dict(os.environ)
    env.update(GIT_ENV_OVERRIDES)
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


def _git(cwd, *args):
    result = _run_git(cwd, *args)
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {cwd}:\n{result.stdout}\n{result.stderr}"
        )
    return result.stdout.strip()


class CreateFindingWorktreeTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="factory-worktree-test-"))
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)

        self.remote = self.tmp_dir / "remote.git"
        _git(self.tmp_dir, "init", "--bare", "--initial-branch=main", str(self.remote))

        seed = self.tmp_dir / "seed"
        _git(self.tmp_dir, "init", "--initial-branch=main", str(seed))
        _git(seed, "remote", "add", "origin", str(self.remote))

        (seed / "file.txt").write_text("A\n", encoding="utf-8")
        _git(seed, "add", "file.txt")
        _git(seed, "commit", "-m", "A: initial commit on main")
        _git(seed, "push", "origin", "main")

        _git(seed, "checkout", "-b", "old-feature")
        (seed / "old.txt").write_text("stale branch\n", encoding="utf-8")
        _git(seed, "add", "old.txt")
        _git(seed, "commit", "-m", "old-feature: unrelated stale work")
        _git(seed, "push", "origin", "old-feature")
        self.stale_sha = _git(seed, "rev-parse", "old-feature")

        _git(seed, "checkout", "main")

        self.clone = self.tmp_dir / "clone"
        _git(self.tmp_dir, "clone", str(self.remote), str(self.clone))

        # Reproduce the observed drift: the clone's cached origin/HEAD
        # symref points at the old feature branch, not at origin/main.
        _git(self.clone, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/old-feature")
        drifted = _git(self.clone, "symbolic-ref", "refs/remotes/origin/HEAD")
        self.assertEqual(drifted, "refs/remotes/origin/old-feature")

        # Advance the real main further on the remote, *after* the drift
        # was introduced and without the clone ever fetching it yet.
        (seed / "file.txt").write_text("A\nB\n", encoding="utf-8")
        _git(seed, "add", "file.txt")
        _git(seed, "commit", "-m", "B: advance main past the drifted HEAD")
        _git(seed, "push", "origin", "main")
        self.current_main_sha = _git(seed, "rev-parse", "main")

        self.assertNotEqual(self.current_main_sha, self.stale_sha)

    def run_script(self, *args):
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=str(self.clone),
            capture_output=True,
            text=True,
        )

    def test_resolve_returns_current_origin_main_not_the_drifted_head(self):
        result = self.run_script("resolve")
        self.assertEqual(result.returncode, 0, result.stderr)
        resolved_sha = result.stdout.strip()

        self.assertEqual(resolved_sha, self.current_main_sha)
        self.assertNotEqual(resolved_sha, self.stale_sha)

        # The drift itself is untouched by `git fetch origin` -- proving
        # that a symref-based resolution would still have picked the
        # stale branch had the script relied on it.
        still_drifted = _git(self.clone, "symbolic-ref", "refs/remotes/origin/HEAD")
        self.assertEqual(still_drifted, "refs/remotes/origin/old-feature")

    def test_create_pins_worktree_to_current_origin_main(self):
        resolve_result = self.run_script("resolve")
        self.assertEqual(resolve_result.returncode, 0, resolve_result.stderr)
        expected_sha = resolve_result.stdout.strip()

        worktree_path = self.tmp_dir / "wt-good"
        create_result = self.run_script(
            "create", expected_sha, str(worktree_path), "fix/P1-DEMO-TEST"
        )
        self.assertEqual(create_result.returncode, 0, create_result.stderr)
        self.assertIn("WORKTREE_READY", create_result.stdout)
        self.assertTrue(worktree_path.exists())

        actual_sha = _git(worktree_path, "rev-parse", "HEAD")
        self.assertEqual(actual_sha, self.current_main_sha)
        self.assertNotEqual(actual_sha, self.stale_sha)

    def _seed_stale_local_branch(self):
        """A leftover local branch from earlier work, pointing at the stale
        commit -- present in the clone before any finding branch is created."""
        _git(self.clone, "branch", "--no-track", "stale-local", self.stale_sha)

    def test_create_needs_no_tracking_write_to_git_config(self):
        """A finding worktree must be creatable without writing .git/config.

        Reproduces the second blocker of the aborted multi-P1 run: a stale
        local branch and a drifted origin/HEAD are both present, and the
        branch is based on a remote-tracking ref. With git's default
        (branch.autoSetupMerge) that combination writes
        branch.<name>.remote/.merge into .git/config -- which the sandbox
        denies, killing branch creation with "could not lock config file".
        The script therefore uses --no-track: the worktree still has to be
        based on the current origin/main tip, but .git/config must come out
        of it byte-for-byte unchanged.
        """
        self._seed_stale_local_branch()

        resolve_result = self.run_script("resolve")
        self.assertEqual(resolve_result.returncode, 0, resolve_result.stderr)
        expected_sha = resolve_result.stdout.strip()

        config_path = self.clone / ".git" / "config"
        config_before = config_path.read_bytes()

        worktree_path = self.tmp_dir / "wt-no-track"
        create_result = self.run_script(
            "create", expected_sha, str(worktree_path), "fix/P1-DEMO-NOTRACK"
        )
        self.assertEqual(create_result.returncode, 0, create_result.stderr)
        self.assertIn("WORKTREE_READY", create_result.stdout)

        # Base is the current origin/main tip -- not the stale local
        # branch, not the drifted origin/HEAD.
        head_sha = _git(worktree_path, "rev-parse", "HEAD")
        self.assertEqual(head_sha, self.current_main_sha)
        self.assertNotEqual(head_sha, self.stale_sha)

        # No write to .git/config was needed at any point.
        self.assertEqual(config_path.read_bytes(), config_before)
        tracking = _run_git(
            self.clone, "config", "--get", "branch.fix/P1-DEMO-NOTRACK.remote"
        )
        self.assertNotEqual(tracking.returncode, 0, tracking.stdout)

    def test_tracking_default_would_require_writing_git_config(self):
        """Negative control for the test above.

        Without --no-track, the very same `git worktree add ... origin/main`
        writes upstream tracking into .git/config. That write is what the
        sandbox refuses, so this proves --no-track is the load-bearing part
        of the fix and not an incidental flag.
        """
        _git(self.clone, "fetch", "origin")

        config_path = self.clone / ".git" / "config"
        config_before = config_path.read_bytes()

        worktree_path = self.tmp_dir / "wt-tracking"
        _git(
            self.clone,
            "worktree",
            "add",
            "-b",
            "fix/P1-DEMO-TRACKING",
            str(worktree_path),
            "origin/main",
        )

        self.assertNotEqual(config_path.read_bytes(), config_before)
        tracking = _git(
            self.clone, "config", "--get", "branch.fix/P1-DEMO-TRACKING.remote"
        )
        self.assertEqual(tracking, "origin")

    def test_canonical_switch_no_track_creates_branch_without_config_write(self):
        """The documented in-repo branch creation (CLAUDE.md, "Finding-Branches")
        must hold under the same conditions: `git switch --no-track -c
        <branch> origin/main` from the repo CWD, based exactly on
        origin/main, with .git/config untouched -- even with a stale local
        branch and a drifted origin/HEAD present.
        """
        self._seed_stale_local_branch()
        _git(self.clone, "fetch", "origin")

        config_path = self.clone / ".git" / "config"
        config_before = config_path.read_bytes()

        switch_result = _run_git(
            self.clone, "switch", "--no-track", "-c", "fix/P1-DEMO-SWITCH", "origin/main"
        )
        self.assertEqual(switch_result.returncode, 0, switch_result.stderr)

        # The two rev-parse checks the workflow demands before writing.
        head_sha = _git(self.clone, "rev-parse", "HEAD")
        origin_main_sha = _git(self.clone, "rev-parse", "origin/main")
        self.assertEqual(head_sha, origin_main_sha)
        self.assertEqual(head_sha, self.current_main_sha)
        self.assertNotEqual(head_sha, self.stale_sha)

        self.assertEqual(config_path.read_bytes(), config_before)
        tracking = _run_git(
            self.clone, "config", "--get", "branch.fix/P1-DEMO-SWITCH.remote"
        )
        self.assertNotEqual(tracking.returncode, 0, tracking.stdout)

    def test_create_discards_worktree_and_blocks_on_sha_mismatch(self):
        worktree_path = self.tmp_dir / "wt-mismatch"
        create_result = self.run_script(
            "create", self.stale_sha, str(worktree_path), "fix/P1-DEMO-MISMATCH"
        )

        self.assertEqual(create_result.returncode, 1)
        self.assertIn("AUTONOMY_BLOCKER", create_result.stderr)
        self.assertFalse(worktree_path.exists())

        worktree_list = _git(self.clone, "worktree", "list")
        self.assertNotIn("wt-mismatch", worktree_list)


if __name__ == "__main__":
    unittest.main()
