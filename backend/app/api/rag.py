"""RAG ingest/search/list/delete endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import Document, get_session
from ..rag.ingest import ingest_text, ingest_upload
from ..rag.store import drop_collection, search

router = APIRouter(prefix="/v1/rag", tags=["rag"])


class IngestTextBody(BaseModel):
    title: str
    text: str
    source_path: Optional[str] = ""
    collection: str = "default"


@router.post("/ingest/text")
async def ingest_text_endpoint(body: IngestTextBody):
    try:
        out = await ingest_text(
            body.text,
            title=body.title,
            source_path=body.source_path or "",
            mime_type="text/plain",
            collection=body.collection,
        )
        return out
    except Exception as e:
        raise HTTPException(500, f"Ingest failed: {e}")


@router.post("/ingest/file")
async def ingest_file_endpoint(
    file: UploadFile = File(...),
    collection: str = Form("default"),
):
    try:
        data = await file.read()
        out = await ingest_upload(file.filename or "upload", data, collection=collection)
        return out
    except Exception as e:
        raise HTTPException(500, f"Ingest failed: {e}")


class SearchBody(BaseModel):
    query: str
    top_k: int = 5
    collection: str = "default"


@router.post("/search")
async def search_endpoint(body: SearchBody):
    try:
        hits = await search(body.query, top_k=body.top_k, collection=body.collection)
        return {"hits": hits}
    except Exception as e:
        raise HTTPException(500, f"Search failed: {e}")


@router.get("/documents")
def list_documents(session: Session = Depends(get_session)):
    rows = session.exec(select(Document).order_by(Document.created_at.desc())).all()
    return [
        {
            "id": d.id,
            "title": d.title,
            "collection": d.collection,
            "source_path": d.source_path,
            "mime_type": d.mime_type,
            "n_chunks": d.n_chunks,
            "created_at": d.created_at.isoformat(),
        }
        for d in rows
    ]


@router.delete("/collections/{collection}")
def delete_collection(collection: str, session: Session = Depends(get_session)):
    dropped = drop_collection(collection)
    # Also remove docs from SQLite
    from ..db import DocumentChunk

    n = 0
    for d in session.exec(select(Document).where(Document.collection == collection)).all():
        session.delete(d)
        n += 1
    for c in session.exec(
        select(DocumentChunk).where(DocumentChunk.collection == collection)
    ).all():
        session.delete(c)
    session.commit()
    return {"dropped_vector_table": dropped, "removed_documents": n}
