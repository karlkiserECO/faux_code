"""Tool tests that exercise the local file-system and sandbox."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.app.tools import ToolContext, get_tool


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "hello.txt").write_text("hello world\n", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "a.py").write_text("def greet():\n    return 'hi'\n", encoding="utf-8")
    return tmp_path


def _ctx(workspace: Path) -> ToolContext:
    return ToolContext(workspace=workspace.resolve())


async def _call(name: str, args: dict, ctx: ToolContext):
    return await get_tool(name).handler(args, ctx)


def test_list_dir(workspace: Path):
    res = asyncio.run(_call("list_dir", {"path": ""}, _ctx(workspace)))
    assert res.ok
    assert "hello.txt" in res.content


def test_read_file(workspace: Path):
    res = asyncio.run(_call("read_file", {"path": "hello.txt"}, _ctx(workspace)))
    assert res.ok
    assert "hello world" in res.content


def test_path_jail(workspace: Path):
    res = asyncio.run(_call("read_file", {"path": "/etc/passwd"}, _ctx(workspace)))
    assert not res.ok
    assert "escapes workspace" in res.content


def test_write_then_read(workspace: Path):
    w = asyncio.run(
        _call("write_file", {"path": "new.txt", "content": "abc"}, _ctx(workspace))
    )
    assert w.ok
    r = asyncio.run(_call("read_file", {"path": "new.txt"}, _ctx(workspace)))
    assert r.ok
    assert "abc" in r.content


def test_edit_file(workspace: Path):
    res = asyncio.run(
        _call(
            "edit_file",
            {"path": "nested/a.py", "find": "'hi'", "replace": "'howdy'"},
            _ctx(workspace),
        )
    )
    assert res.ok
    text = (workspace / "nested" / "a.py").read_text()
    assert "'howdy'" in text


def test_grep(workspace: Path):
    res = asyncio.run(_call("grep", {"pattern": "greet"}, _ctx(workspace)))
    assert res.ok
    assert "a.py" in res.content


def test_python_sandbox(workspace: Path):
    res = asyncio.run(
        _call("python", {"code": "print(40 + 2)"}, _ctx(workspace))
    )
    assert res.ok
    assert "42" in res.content


def test_shell_sandbox(workspace: Path):
    res = asyncio.run(_call("shell", {"command": "ls"}, _ctx(workspace)))
    assert res.ok
    assert "hello.txt" in res.content


def test_python_timeout(workspace: Path):
    res = asyncio.run(
        _call(
            "python",
            {"code": "import time; time.sleep(5)", "timeout_sec": 1},
            _ctx(workspace),
        )
    )
    assert not res.ok
    assert res.data.get("timed_out") is True
