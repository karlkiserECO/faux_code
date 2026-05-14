"""RAG search tool — queries the local LanceDB collections.

Returns an empty result gracefully if no collections exist yet, so the tool can
always be exposed to the model.
"""

from __future__ import annotations

from typing import Any

from .registry import Tool, ToolContext, ToolResult, register


async def rag_search_handler(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    query = (args.get("query") or "").strip()
    if not query:
        return ToolResult(ok=False, is_error=True, content="Missing 'query'.")
    top_k = int(args.get("top_k", 5))
    collection = (args.get("collection") or "default").strip() or "default"

    try:
        from ..rag.store import search  # lazy import to avoid heavy boot
    except Exception as e:
        return ToolResult(
            ok=False,
            is_error=True,
            content=f"RAG not available: {e}",
        )

    try:
        hits = await search(query, top_k=top_k, collection=collection)
    except FileNotFoundError:
        return ToolResult(ok=True, content="(no documents ingested yet)", data={"hits": []})
    except Exception as e:
        return ToolResult(ok=False, is_error=True, content=f"RAG search failed: {e}")

    if not hits:
        return ToolResult(ok=True, content="(no matches)", data={"hits": []})
    lines = [f"### RAG search: {query}", f"_collection: {collection}_", ""]
    for i, h in enumerate(hits, 1):
        lines.append(
            f"**{i}. {h.get('title', '(untitled)')}** "
            f"(score {h.get('score', 0):.3f})\n{h.get('text', '')[:600]}\n"
        )
    return ToolResult(ok=True, content="\n".join(lines), data={"hits": hits})


register(
    Tool(
        name="rag_search",
        description=(
            "Search the local knowledge base (ingested documents) by semantic similarity. "
            "Use when the user references uploaded files or asks about local docs."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
                "collection": {"type": "string", "default": "default"},
            },
            "required": ["query"],
        },
        writes=False,
        handler=rag_search_handler,
    )
)
