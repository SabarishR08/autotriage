import pytest

from app.services.llm_provider import LLMProviderError, _parse_json_response


def test_parse_json_response_plain():
    raw = '{"root_cause": "null pointer", "affected_files": ["a.py"], "confidence": "high", "suggested_fix": "add null check", "patch_diff": null}'
    result = _parse_json_response(raw)
    assert result["root_cause"] == "null pointer"
    assert result["affected_files"] == ["a.py"]


def test_parse_json_response_with_markdown_fence():
    raw = '```json\n{"root_cause": "x", "affected_files": [], "confidence": "low", "suggested_fix": "y", "patch_diff": null}\n```'
    result = _parse_json_response(raw)
    assert result["root_cause"] == "x"


def test_parse_json_response_invalid_raises():
    with pytest.raises(LLMProviderError):
        _parse_json_response("not json at all")
