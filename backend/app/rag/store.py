"""LanceDB-backed vector store. Lazy-imported because lancedb pulls heavy deps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..settings import get_settings

_TABLE_NAMES: set[str] = set()


def _db_path() -> Path:
    s = get_settings()
    p = s.data_dir / "lancedb"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _connect():
    import lancedb

    return lancedb.connect(str(_db_path()))


async def _embed(texts: list[str]) -> list[list[float]]:
    """Embed texts with the configured local Ollama model."""
    from ..providers import get_provider
    from ..providers.ollama import OllamaProvider

    p = get_provider("ollama")
    assert isinstance(p, OllamaProvider)
    model = get_settings().ollama_default_embed
    return await p.embed(model, texts)


async def upsert_chunks(
    collection: str,
    chunks: list[dict[str, Any]],
) -> int:
    """Insert chunks (`{id, document_id, text, title, source_path, chunk_index}`)."""
    import pyarrow as pa

    if not chunks:
        return 0
    embeddings = await _embed([c["text"] for c in chunks])
    if not embeddings or not embeddings[0]:
        raise RuntimeError("Embedding model returned empty vectors (is Ollama embed model pulled?)")

    db = _connect()
    table_name = f"chunks_{collection}"
    rows = []
    for c, vec in zip(chunks, embeddings):
        rows.append(
            {
                "id": c["id"],
                "document_id": c.get("document_id", ""),
                "title": c.get("title", ""),
                "source_path": c.get("source_path", ""),
                "chunk_index": c.get("chunk_index", 0),
                "text": c["text"],
                "vector": vec,
            }
        )
    schema = pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("document_id", pa.string()),
            pa.field("title", pa.string()),
            pa.field("source_path", pa.string()),
            pa.field("chunk_index", pa.int64()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), list_size=len(embeddings[0]))),
        ]
    )
    if table_name in db.table_names():
        table = db.open_table(table_name)
        table.add(rows)
    else:
        table = db.create_table(table_name, data=rows, schema=schema)
    _TABLE_NAMES.add(table_name)
    return len(rows)


async def search(query: str, top_k: int = 5, collection: str = "default") -> list[dict[str, Any]]:
    db = _connect()
    table_name = f"chunks_{collection}"
    if table_name not in db.table_names():
        return []
    table = db.open_table(table_name)
    vec = (await _embed([query]))[0]
    results = table.search(vec).limit(top_k).to_list()
    out = []
    for r in results:
        out.append(
            {
                "id": r.get("id"),
                "document_id": r.get("document_id"),
                "title": r.get("title"),
                "source_path": r.get("source_path"),
                "chunk_index": r.get("chunk_index"),
                "text": r.get("text"),
                "score": float(1.0 / (1.0 + (r.get("_distance", 0.0) or 0.0))),
            }
        )
    return out


def drop_collection(collection: str) -> bool:
    db = _connect()
    table_name = f"chunks_{collection}"
    if table_name in db.table_names():
        db.drop_table(table_name)
        return True
    return False
