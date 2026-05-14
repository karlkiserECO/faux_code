"""Fetch a web page and return its readable content as markdown."""

from __future__ import annotations

from typing import Any

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify

from .registry import Tool, ToolContext, ToolResult, register

MAX_BYTES = 5 * 1024 * 1024
MAX_MARKDOWN_CHARS = 80_000


async def web_fetch_handler(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    url = (args.get("url") or "").strip()
    if not url:
        return ToolResult(ok=False, is_error=True, content="Missing 'url'.")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    as_text = bool(args.get("as_text", False))
    max_chars = int(args.get("max_chars", MAX_MARKDOWN_CHARS))
    max_chars = max(1000, min(MAX_MARKDOWN_CHARS, max_chars))

    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": "faux_code/0.1 (+https://github.com/karl-kiser/faux_code)"},
        ) as client:
            async with client.stream("GET", url) as r:
                if r.status_code >= 400:
                    return ToolResult(
                        ok=False,
                        is_error=True,
                        content=f"HTTP {r.status_code} fetching {url}",
                    )
                content_type = r.headers.get("Content-Type", "")
                buf = bytearray()
                async for chunk in r.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) >= MAX_BYTES:
                        break
                body = bytes(buf)
    except Exception as e:
        return ToolResult(ok=False, is_error=True, content=f"Fetch error: {e}")

    if as_text or "text/" not in content_type and "html" not in content_type:
        text = body.decode("utf-8", errors="replace")[:max_chars]
        return ToolResult(
            ok=True,
            content=f"### {url}\n\n```\n{text}\n```",
            data={"url": url, "content_type": content_type, "bytes": len(body)},
        )

    html = body.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "iframe", "svg", "form"]):
        tag.decompose()

    title = (soup.title.string.strip() if soup.title and soup.title.string else url)

    # Prefer <main> / <article> if available, fall back to <body>.
    root = soup.find("main") or soup.find("article") or soup.body or soup
    md = markdownify(str(root), heading_style="ATX", bullets="-")
    md = "\n".join(line.rstrip() for line in md.splitlines() if line.strip())
    if len(md) > max_chars:
        md = md[:max_chars] + "\n\n…[truncated]"

    return ToolResult(
        ok=True,
        content=f"### {title}\n\n_URL: {url}_\n\n{md}",
        data={"url": url, "title": title, "content_type": content_type, "bytes": len(body)},
    )


register(
    Tool(
        name="web_fetch",
        description=(
            "Fetch a single URL and return its main readable content as markdown. "
            "Use after web_search to read a specific result."
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch (http/https)."},
                "as_text": {
                    "type": "boolean",
                    "description": "If true, return raw text instead of parsed markdown.",
                    "default": False,
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Max characters to return.",
                    "default": MAX_MARKDOWN_CHARS,
                },
            },
            "required": ["url"],
        },
        writes=False,
        handler=web_fetch_handler,
    )
)
