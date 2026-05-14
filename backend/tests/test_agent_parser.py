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


def test_multiple_calls_separated_by_qwen_tokens():
    """Qwen variants emit chained tool calls separated by template markers."""
    text = (
        '{"name": "edit_file", "arguments": {"path": "a.py", "find": "x", "replace": "y"}}\n'
        '<|im_start|>assistant\n'
        '{"name": "edit_file", "arguments": {"path": "b.py", "find": "x", "replace": "y"}}'
    )
    calls = _extract_json_tool_calls(text)
    assert len(calls) == 2
    assert calls[0].arguments["path"] == "a.py"
    assert calls[1].arguments["path"] == "b.py"


def test_two_distinct_calls_in_one_message():
    text = (
        '{"name": "read_file", "arguments": {"path": "a.py"}}\n'
        'and then\n'
        '{"name": "read_file", "arguments": {"path": "b.py"}}'
    )
    calls = _extract_json_tool_calls(text)
    assert len(calls) == 2
    paths = sorted(c.arguments["path"] for c in calls)
    assert paths == ["a.py", "b.py"]


def test_balanced_braces_inside_strings():
    """JSON containing curly braces inside string values should still parse cleanly."""
    text = '{"name": "shell", "arguments": {"command": "echo \\"{hello}\\""}}'
    calls = _extract_json_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "shell"
    assert "{hello}" in calls[0].arguments["command"]


# --- Plan-detection tests ---

from backend.app.agent.loop import _looks_like_plan  # noqa: E402


def test_plan_detector_catches_lets_read():
    assert _looks_like_plan("Let's read both files to understand the problem.")


def test_plan_detector_catches_ill_run():
    assert _looks_like_plan("I'll run python3 test_math.py again to verify.")


def test_plan_detector_catches_step_one():
    assert _looks_like_plan("Step 1: I will inspect the failing test.\nStep 2: fix it.")


def test_plan_detector_catches_please_confirm():
    assert _looks_like_plan(
        "If confirmed, I'll replace all occurrences. Please confirm if you want me to proceed."
    )


def test_plan_detector_catches_should_i():
    assert _looks_like_plan("Should I edit both files or just the first?")


def test_plan_detector_ignores_real_answer():
    assert not _looks_like_plan("The capital of France is Paris.")


def test_plan_detector_ignores_long_explanation():
    text = "Here is a long detailed explanation that includes various words. " * 30
    # Long-form prose is almost always a real answer, not a stalled plan.
    assert not _looks_like_plan(text)
