"""Web search tool — Tavily preferred, DuckDuckGo fallback, SearXNG optional."""

from __future__ import annotations

from typing import Any

import httpx

from ..settings import get_settings
from .registry import Tool, ToolContext, ToolResult, register


async def _tavily_search(query: str, max_results: int, api_key: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "include_answer": "basic",
                "search_depth": "basic",
            },
        )
        r.raise_for_status()
        data = r.json()
        results = []
        if data.get("answer"):
            results.append(
                {"title": "Tavily summary", "url": "", "snippet": data["answer"]}
            )
        for item in data.get("results", []):
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", ""),
                }
            )
        return results


async def _ddg_search(query: str, max_results: int) -> list[dict]:
    try:
        from ddgs import DDGS  # new package name
    except ImportError:
        from duckduckgo_search import DDGS  # legacy fallback

    out: list[dict] = []
    with DDGS() as ddg:
        for hit in ddg.text(query, max_results=max_results):
            out.append(
                {
                    "title": hit.get("title", ""),
                    "url": hit.get("href") or hit.get("url", ""),
                    "snippet": hit.get("body", ""),
                }
            )
    return out


async def _wikipedia_search(query: str, max_results: int) -> list[dict]:
    """Free, no-auth fallback for general knowledge."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": max_results,
            },
        )
        r.raise_for_status()
        data = r.json()
        out: list[dict] = []
        for item in data.get("query", {}).get("search", []):
            title = item.get("title", "")
            snippet_html = item.get("snippet", "")
            from bs4 import BeautifulSoup

            snippet = BeautifulSoup(snippet_html, "lxml").get_text(" ", strip=True)
            out.append(
                {
                    "title": title,
                    "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    "snippet": snippet,
                }
            )
        return out


async def _searxng(query: str, max_results: int, base_url: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            f"{base_url.rstrip('/')}/search",
            params={"q": query, "format": "json", "safesearch": 0},
        )
        r.raise_for_status()
        data = r.json()
        out = []
        for item in data.get("results", [])[:max_results]:
            out.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", ""),
                }
            )
        return out


async def web_search_handler(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    query = (args.get("query") or "").strip()
    if not query:
        return ToolResult(ok=False, is_error=True, content="Missing 'query'.")
    max_results = int(args.get("max_results", 6))
    max_results = max(1, min(15, max_results))

    s = get_settings()
    errors: list[str] = []

    if s.tavily_api_key:
        try:
            hits = await _tavily_search(query, max_results, s.tavily_api_key)
            if hits:
                return _format_hits(query, "tavily", hits)
        except Exception as e:
            errors.append(f"tavily: {e}")

    if s.searxng_base_url:
        try:
            hits = await _searxng(query, max_results, s.searxng_base_url)
            if hits:
                return _format_hits(query, "searxng", hits)
        except Exception as e:
            errors.append(f"searxng: {e}")

    try:
        hits = await _ddg_search(query, max_results)
        if hits:
            return _format_hits(query, "duckduckgo", hits)
        errors.append("duckduckgo: no results")
    except Exception as e:
        errors.append(f"duckduckgo: {e}")

    try:
        hits = await _wikipedia_search(query, max_results)
        if hits:
            return _format_hits(query, "wikipedia", hits)
        errors.append("wikipedia: no results")
    except Exception as e:
        errors.append(f"wikipedia: {e}")

    return ToolResult(
        ok=False, is_error=True, content="Web search failed: " + "; ".join(errors)
    )


def _format_hits(query: str, source: str, hits: list[dict]) -> ToolResult:
    lines = [f"### Web search results for: {query}", f"_source: {source}_", ""]
    for i, h in enumerate(hits, 1):
        title = h.get("title") or "(untitled)"
        url = h.get("url") or ""
        snippet = (h.get("snippet") or "").replace("\n", " ").strip()
        lines.append(f"**{i}. {title}**")
        if url:
            lines.append(url)
        if snippet:
            lines.append(snippet[:400])
        lines.append("")
    return ToolResult(
        ok=True,
        content="\n".join(lines),
        data={"results": hits, "source": source, "query": query},
    )


register(
    Tool(
        name="web_search",
        description=(
            "Search the public web for information. Returns a ranked list of result "
            "titles, URLs, and snippets. Use this when the user asks about current "
            "events, facts you don't know, or anything that requires fresh info."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "max_results": {
                    "type": "integer",
                    "description": "Max results (1-15).",
                    "default": 6,
                },
            },
            "required": ["query"],
        },
        writes=False,
        handler=web_search_handler,
    )
)
