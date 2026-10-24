import importlib
import json

import pytest


@pytest.fixture
def tool():
    return importlib.import_module("scripts.diagnostic_contract")


def test_whitelist_projection_never_copies_free_text(tool):
    secret = "sk-PRIVATE_SENTINEL"
    payload = {k: secret for k in ("api_key", "title", "path", "source_url", "error", "logs", "env", "model")}
    payload.update(mode="portable", stage="summarizing", error_code="llm_unavailable",
                   model_kind="remote", segment_count=7, duration_seconds=1.25,
                   nested={"secret": secret}, version=secret)
    result = tool.build_snapshot(payload, {"os": "Windows", "os_major": 10, "python": "3.13.2",
                                            "packages": {"openai": "2.1.0", "private": secret}})
    assert result["schema_version"] == 1
    assert result["runtime"]["segment_count"] == 7
    assert result["environment"]["packages"]["openai"] == "2.1.0"
    assert secret not in json.dumps(result)
    assert result["product"] == "Video2Knowledge"


@pytest.mark.parametrize("value", ["C:\\private\\user", "sk-secret", "3.1.0+PRIVATE", "3.1\nsecret", "", [], None])
def test_strict_versions_reject_unknown_suffix_or_paths(tool, value):
    assert tool.safe_version(value) is None


@pytest.mark.parametrize("value", ["3.13.2", "6.22.3", "1.0.0b3", "2.0.0rc1", "1.2.0.post1", "1.0.0-beta.3"])
def test_safe_versions(tool, value):
    assert tool.safe_version(value) == value


@pytest.mark.parametrize("value", [True, -1, float("inf"), float("nan"), "5", 10**15, 10**1000])
def test_invalid_numeric_fields_not_exported(tool, value):
    result = tool.build_snapshot({"duration_seconds": value, "segment_count": value}, {})
    assert result["runtime"]["duration_seconds"] is None
    assert result["runtime"]["segment_count"] is None


def test_unknown_enum_is_unknown_and_bad_inputs_do_not_raise(tool):
    result = tool.build_snapshot({"mode": "C:/private", "stage": "KEY", "error_code": "KEY"}, {})
    assert set(result["runtime"][k] for k in ("mode", "stage", "error_code")) == {"unknown"}
    assert tool.build_snapshot(None, []) == tool.build_snapshot({}, {})
