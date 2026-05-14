"""Workspace browsing + editing API.

The frontend Code workspace surface uses this to populate the file tree, open
files in Monaco, and save edits. All paths are constrained to the configured
workspace root.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..settings import get_settings

router = APIRouter(prefix="/v1/workspace", tags=["workspace"])

MAX_TREE_ENTRIES = 5000
MAX_READ_BYTES = 2 * 1024 * 1024
SKIP_DIRS = {".git", ".venv", "node_modules", ".next", "__pycache__", "dist", "build", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache"}


def _root(custom: Optional[str] = None) -> Path:
    if custom:
        p = Path(custom).expanduser().resolve()
    else:
        p = get_settings().workspace_root.resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _inside(root: Path, rel: str) -> Path:
    if not rel or rel == ".":
        return root
    target = (root / rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise HTTPException(400, "Path escapes workspace")
    return target


@router.get("/info")
def info(root: Optional[str] = None):
    r = _root(root)
    return {
        "root": str(r),
        "exists": r.exists(),
    }


@router.get("/tree")
def tree(root: Optional[str] = None, path: str = ""):
    r = _root(root)
    target = _inside(r, path)
    if not target.exists():
        raise HTTPException(404, "Not found")
    if target.is_file():
        return [
            {
                "name": target.name,
                "path": str(target.relative_to(r)),
                "is_dir": False,
                "size": target.stat().st_size,
            }
        ]
    out = []
    try:
        for p in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if p.name in SKIP_DIRS:
                continue
            if p.name.startswith(".DS_Store"):
                continue
            try:
                size = p.stat().st_size if p.is_file() else None
            except OSError:
                size = None
            out.append(
                {
                    "name": p.name,
                    "path": str(p.relative_to(r)),
                    "is_dir": p.is_dir(),
                    "size": size,
                }
            )
            if len(out) >= MAX_TREE_ENTRIES:
                break
    except PermissionError:
        raise HTTPException(403, "Permission denied")
    return out


@router.get("/file")
def read_file(path: str, root: Optional[str] = None):
    r = _root(root)
    target = _inside(r, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "Not a file")
    size = target.stat().st_size
    if size > MAX_READ_BYTES:
        raise HTTPException(413, f"File too large ({size} bytes)")
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(500, f"Read error: {e}")
    return {
        "path": str(target.relative_to(r)),
        "size": size,
        "content": text,
    }


class WriteBody(BaseModel):
    path: str
    content: str
    root: Optional[str] = None


@router.post("/file")
def write_file(body: WriteBody):
    r = _root(body.root)
    target = _inside(r, body.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_text(body.content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(500, f"Write error: {e}")
    return {
        "path": str(target.relative_to(r)),
        "size": len(body.content),
        "ok": True,
    }
