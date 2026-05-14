"""Tests for the agent loop's fallback tool-call parser.

This parser exists because some models (notably Qwen variants on Ollama) emit
tool calls as JSON in the assistant text content instead of the structured
`tool_calls` field. We must recover those.
"""

from __future__ import annotations

from backend.app.agent.loop import _extract_json_tool_calls


def test_bare_openai_compat_json():
    text = '{"name": "read_file", "arguments": {"path": "README.md"}}'
    calls = _extract_json_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "read_file"
    assert calls[0].arguments == {"path": "README.md"}


def test_parameters_alias():
    text = '{"name": "shell", "parameters": {"command": "ls"}}'
    calls = _extract_json_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].arguments == {"command": "ls"}


def test_json_fenced():
    text = """Sure, I'll do that.

```json
{"name": "write_file", "arguments": {"path": "x.py", "content": "print(1)"}}
```
"""
    calls = _extract_json_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "write_file"


def test_tool_call_fence():
    text = """```tool_call
{"name": "grep", "arguments": {"pattern": "foo"}}
```"""
    calls = _extract_json_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "grep"


def test_array_of_calls():
    text = '[{"name": "list_dir", "arguments": {}}, {"name": "read_file", "arguments": {"path": "a"}}]'
    calls = _extract_json_tool_calls(text)
    assert len(calls) == 2
    assert calls[0].name == "list_dir"
    assert calls[1].name == "read_file"


def test_string_arguments():
    text = '{"name": "shell", "arguments": "{\\"command\\": \\"ls\\"}"}'
    calls = _extract_json_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].arguments == {"command": "ls"}


def test_openai_nested_function_form():
    text = '{"id": "c1", "type": "function", "function": {"name": "shell", "arguments": "{\\"command\\": \\"ls\\"}"}}'
    calls = _extract_json_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].id == "c1"
    assert calls[0].name == "shell"


def test_plain_prose_returns_nothing():
    text = "I'll go ahead and read the file now."
    calls = _extract_json_tool_calls(text)
    assert calls == []


def test_tool_call_tag_prefix():
    text = '<tool_call>\n{"name": "list_dir", "arguments": {}}\n</tool_call>'
    calls = _extract_json_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "list_dir"


def test_dedup():
    text = '[{"name": "x", "arguments": {"a": 1}}, {"name": "x", "arguments": {"a": 1}}]'
    calls = _extract_json_tool_calls(text)
    assert len(calls) == 1
