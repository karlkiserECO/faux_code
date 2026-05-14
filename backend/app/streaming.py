"""SSE streaming helpers.

We emit a small unified event format so the frontend doesn't need to understand
each provider's wire protocol.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any


def sse_format(event: str, data: Any) -> str:
    """Format an SSE message (event + data lines)."""
    if not isinstance(data, str):
        data = json.dumps(data, ensure_ascii=False, default=str)
    out_lines = [f"event: {event}"]
    for line in data.splitlines() or [""]:
        out_lines.append(f"data: {line}")
    return "\n".join(out_lines) + "\n\n"


async def event_stream(generator: AsyncIterator[dict]) -> AsyncIterator[bytes]:
    """Convert an async iterator of dict events to SSE bytes."""
    try:
        async for ev in generator:
            event_name = ev.get("event", "message")
            data = ev.get("data", "")
            yield sse_format(event_name, data).encode("utf-8")
    except Exception as exc:  # pragma: no cover - defensive
        yield sse_format("error", {"message": str(exc)}).encode("utf-8")
    finally:
        yield sse_format("done", "").encode("utf-8")
