"""Tests for the new git_* and apply_patch tools."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.app.tools import ToolContext, get_tool

GIT = shutil.which("git")


def _ctx(workspace: Path) -> ToolContext:
    return ToolContext(workspace=workspace.resolve())


async def _call(name: str, args: dict, ctx: ToolContext):
    return await get_tool(name).handler(args, ctx)


def _git(workspace: Path, *args: str) -> subprocess.CompletedProcess:
    """Run a git command in the workspace with a clean env, raising on failure."""
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_AUTHOR_NAME"] = "Test User"
    env["GIT_AUTHOR_EMAIL"] = "test@example.com"
    env["GIT_COMMITTER_NAME"] = "Test User"
    env["GIT_COMMITTER_EMAIL"] = "test@example.com"
    return subprocess.run(
        ["git", *args],
        cwd=str(workspace),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    if GIT is None:
        pytest.skip("git not available")
    init = subprocess.run(
        [GIT, "init", "-b", "main", str(tmp_path)], capture_output=True
    )
    if init.returncode != 0:
        subprocess.run([GIT, "init", str(tmp_path)], capture_output=True, check=True)
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    return tmp_path


def test_git_status_on_clean_repo(repo: Path):
    res = asyncio.run(_call("git_status", {}, _ctx(repo)))
    assert res.ok, res.content
    text = res.content.lower()
    assert "main" in text or "master" in text


def test_git_status_shows_untracked(repo: Path):
    (repo / "new.txt").write_text("hello\n", encoding="utf-8")
    res = asyncio.run(_call("git_status", {}, _ctx(repo)))
    assert res.ok, res.content
    assert "new.txt" in res.content
    assert "untracked" in res.content.lower()


def test_git_diff_shows_changes(repo: Path):
    (repo / "a.txt").write_text("original\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "init", "--no-verify")
    (repo / "a.txt").write_text("modified\n", encoding="utf-8")
    res = asyncio.run(_call("git_diff", {}, _ctx(repo)))
    assert res.ok, res.content
    assert "-original" in res.content
    assert "+modified" in res.content


def test_git_diff_truncates(repo: Path):
    big = "\n".join(f"line {i}" for i in range(100)) + "\n"
    (repo / "big.txt").write_text(big, encoding="utf-8")
    _git(repo, "add", "big.txt")
    _git(repo, "commit", "-m", "init big", "--no-verify")
    (repo / "big.txt").write_text(
        "\n".join(f"changed {i}" for i in range(100)) + "\n", encoding="utf-8"
    )
    res = asyncio.run(_call("git_diff", {"max_lines": 5}, _ctx(repo)))
    assert res.ok, res.content
    assert res.data.get("truncated") is True
    assert "truncated" in res.content.lower()


def test_git_log_after_commit(repo: Path):
    (repo / "a.txt").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "feat: initial commit", "--no-verify")
    res = asyncio.run(_call("git_log", {"limit": 10}, _ctx(repo)))
    assert res.ok, res.content
    assert "feat: initial commit" in res.content
    assert res.data.get("commits"), "expected at least one commit in data"


def test_git_status_outside_repo(tmp_path: Path):
    """Plain (non-git) directory should fail with a helpful message."""
    if GIT is None:
        pytest.skip("git not available")
    res = asyncio.run(_call("git_status", {}, _ctx(tmp_path)))
    assert not res.ok
    assert "not a git repository" in res.content.lower()


def test_apply_patch_creates_file(repo: Path):
    if GIT is None:
        pytest.skip("git not available")
    patch = (
        "diff --git a/new.txt b/new.txt\n"
        "new file mode 100644\n"
        "index 0000000..b6fc4c6\n"
        "--- /dev/null\n"
        "+++ b/new.txt\n"
        "@@ -0,0 +1 @@\n"
        "+hello\n"
    )
    res = asyncio.run(_call("apply_patch", {"patch": patch}, _ctx(repo)))
    assert res.ok, res.content
    assert (repo / "new.txt").read_text(encoding="utf-8") == "hello\n"


def test_apply_patch_modifies_file(repo: Path):
    if GIT is None:
        pytest.skip("git not available")
    (repo / "a.txt").write_text("original\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "init", "--no-verify")
    patch = (
        "diff --git a/a.txt b/a.txt\n"
        "--- a/a.txt\n"
        "+++ b/a.txt\n"
        "@@ -1 +1 @@\n"
        "-original\n"
        "+modified\n"
    )
    res = asyncio.run(_call("apply_patch", {"patch": patch}, _ctx(repo)))
    assert res.ok, res.content
    assert (repo / "a.txt").read_text(encoding="utf-8") == "modified\n"


def test_apply_patch_path_jail(repo: Path):
    if GIT is None:
        pytest.skip("git not available")
    patch = (
        "diff --git a/../escape.txt b/../escape.txt\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/../escape.txt\n"
        "@@ -0,0 +1 @@\n"
        "+pwn\n"
    )
    res = asyncio.run(_call("apply_patch", {"patch": patch}, _ctx(repo)))
    assert not res.ok
    assert "escape" in res.content.lower() or "rejected" in res.content.lower()
    assert not (repo.parent / "escape.txt").exists()


def test_apply_patch_missing_patch(repo: Path):
    res = asyncio.run(_call("apply_patch", {"patch": ""}, _ctx(repo)))
    assert not res.ok
    assert "missing" in res.content.lower() or "empty" in res.content.lower()


def test_apply_patch_invalid_patch(repo: Path):
    """A malformed patch should fail gracefully with both backends reported."""
    if GIT is None:
        pytest.skip("git not available")
    res = asyncio.run(
        _call(
            "apply_patch",
            {"patch": "this is not a valid patch at all\n"},
            _ctx(repo),
        )
    )
    assert not res.ok
    assert "git apply" in res.content.lower() or "patch" in res.content.lower()
