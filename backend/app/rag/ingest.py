"""Document ingestion: extract text -> chunk -> embed -> upsert."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlmodel import Session

from ..db import Document, DocumentChunk
from ..db.session import _get_engine
from .store import upsert_chunks


def _extract_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n\n".join(parts)


def _extract_pdf_bytes(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n\n".join(parts)


def _chunk(text: str, *, max_chars: int = 1800, overlap: int = 200) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        end = min(n, i + max_chars)
        # Try to break on a paragraph or sentence boundary near `end`.
        if end < n:
            for sep in ("\n\n", "\n", ". ", "! ", "? "):
                idx = text.rfind(sep, i + int(max_chars * 0.5), end)
                if idx != -1:
                    end = idx + len(sep)
                    break
        chunks.append(text[i:end].strip())
        if end >= n:
            break
        i = max(i + 1, end - overlap)
    return [c for c in chunks if c]


async def ingest_text(
    text: str,
    *,
    title: str,
    source_path: str = "",
    mime_type: str = "text/plain",
    collection: str = "default",
) -> dict[str, Any]:
    chunks = _chunk(text)
    if not chunks:
        return {"document_id": None, "chunks": 0, "skipped": "empty"}

    doc = Document(
        collection=collection,
        title=title,
        source_path=source_path,
        mime_type=mime_type,
        n_chunks=len(chunks),
    )
    chunk_rows: list[dict[str, Any]] = []
    db_chunks: list[DocumentChunk] = []
    for i, c in enumerate(chunks):
        chunk_id = str(uuid4())
        chunk_rows.append(
            {
                "id": chunk_id,
                "document_id": doc.id,
                "title": title,
                "source_path": source_path,
                "chunk_index": i,
                "text": c,
            }
        )
        db_chunks.append(
            DocumentChunk(
                id=chunk_id,
                document_id=doc.id,
                collection=collection,
                chunk_index=i,
                text=c,
            )
        )

    await upsert_chunks(collection, chunk_rows)

    with Session(_get_engine()) as s:
        s.add(doc)
        for c in db_chunks:
            s.add(c)
        s.commit()
        s.refresh(doc)

    return {"document_id": doc.id, "chunks": len(chunks), "title": title}


async def ingest_file(path: str | Path, collection: str = "default") -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        text = _extract_pdf(p)
        mime = "application/pdf"
    else:
        text = p.read_text(encoding="utf-8", errors="replace")
        mime = "text/plain"
    return await ingest_text(
        text,
        title=p.name,
        source_path=str(p.resolve()),
        mime_type=mime,
        collection=collection,
    )


async def ingest_upload(filename: str, data: bytes, collection: str = "default") -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        text = _extract_pdf_bytes(data)
        mime = "application/pdf"
    else:
        text = data.decode("utf-8", errors="replace")
        mime = "text/plain"
    return await ingest_text(
        text,
        title=filename,
        source_path=f"upload://{filename}",
        mime_type=mime,
        collection=collection,
    )
