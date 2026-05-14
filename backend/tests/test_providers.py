"""Provider adapter tests — don't hit real APIs (we mock httpx)."""

from __future__ import annotations

from backend.app.providers.openai_compat import _messages_to_openai, _tools_to_openai
from backend.app.providers.base import ChatMessage, ToolDef, ToolCall


def test_messages_roundtrip():
    msgs = [
        ChatMessage(role="system", content="be brief"),
        ChatMessage(role="user", content="hi"),
        ChatMessage(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="c1", name="read_file", arguments={"path": "a.txt"})],
        ),
        ChatMessage(role="tool", content="contents", tool_call_id="c1", name="read_file"),
    ]
    out = _messages_to_openai(msgs)
    assert out[0] == {"role": "system", "content": "be brief"}
    assert out[2]["tool_calls"][0]["function"]["name"] == "read_file"
    assert out[3]["tool_call_id"] == "c1"


def test_tools_format():
    tools = [
        ToolDef(name="x", description="desc", parameters={"type": "object", "properties": {"a": {"type": "string"}}})
    ]
    out = _tools_to_openai(tools)
    assert out[0]["type"] == "function"
    assert out[0]["function"]["name"] == "x"
    assert out[0]["function"]["parameters"]["properties"]["a"]["type"] == "string"
