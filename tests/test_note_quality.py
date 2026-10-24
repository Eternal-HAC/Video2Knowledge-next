"""Offline evaluation checks, never a model quality/accuracy benchmark."""
import copy
import importlib
import json
import socket
import subprocess

import pytest


@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("offline tools must not contact external services")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)


@pytest.fixture
def tool():
    return importlib.import_module("scripts.evaluate_notes")


def test_twelve_cases_cover_all_templates_and_pass(tool):
    cases = tool.load_cases()
    assert len(cases) == 12
    assert len({c["id"] for c in cases}) == 12
    assert len({c["template_id"] for c in cases}) == 6
    assert all(3 <= len(c["required_points"]) <= 8 for c in cases)
    report = tool.evaluate_suite()
    assert report["passed"] and report["case_count"] == 12
    assert report["mode"] == "reference_rules_only"
    assert "accuracy" not in json.dumps(report)
    for case in cases:
        assert tool.evaluate_case(case, tool.reference_note(case))["passed"]


@pytest.mark.parametrize("mutation,code", [
    ("point", "missing_point"), ("literal", "missing_literal"),
    ("tail", "missing_point"), ("frontmatter", "frontmatter_invalid"),
    ("metadata", "frontmatter_metadata"), ("clock", "timestamp_invalid"),
    ("range", "timestamp_unmapped"), ("no_clock", "timestamp_missing"),
    ("attachment", "attachment_unsafe"), ("undeclared", "attachment_undeclared"),
    ("html_image", "attachment_unsafe"), ("forbidden", "forbidden_literal"),
    ("blank", "body_empty"),
])
def test_mutations_fail_without_echoing_content(tool, mutation, code):
    case = next(c for c in tool.load_cases() if c["id"] == "number-units")
    note = tool.reference_note(case)
    if mutation in {"point", "tail"}:
        point = case["required_points"][-1 if mutation == "tail" else 0]
        for literal in point["any_of"]:
            note = note.replace(literal, "已移除")
    elif mutation == "literal":
        note = note.replace(case["required_literals"][0], "999 ms")
    elif mutation == "frontmatter":
        note = "---\ninvalid: [\n---\n" + note.split("---", 2)[-1]
    elif mutation == "metadata":
        note = note.replace("subtitle_import", "other")
    elif mutation == "clock":
        note += "\n[00:99-00:99]"
    elif mutation == "range":
        note += "\n[09:00-09:02]"
    elif mutation == "no_clock":
        note = tool.CITATION_RE.sub("", note)
    elif mutation == "attachment":
        note += "\n![图](../private.png)"
    elif mutation == "undeclared":
        note += "\n![图](frames/missing.png)"
    elif mutation == "html_image":
        note += '<img src="https://invalid.example/key">'
    elif mutation == "forbidden":
        note += "\n" + case["forbidden_literals"][0]
    elif mutation == "blank":
        note = note.split("---", 2)[0] + "---" + note.split("---", 2)[1] + "---\n"
    result = tool.evaluate_case(case, note)
    assert not result["passed"] and code in result["failures"]
    assert "999 ms" not in json.dumps(result)


def test_alternative_wording_not_full_text_snapshot(tool):
    case = tool.load_cases()[0]
    note = tool.reference_note(case).replace("## 核心概念", "## 我的学习记录")
    point = case["required_points"][0]
    assert len(point["any_of"]) > 1
    note = note.replace(point["any_of"][0], point["any_of"][1])
    assert tool.evaluate_case(case, note)["passed"]


def test_literal_placeholder_remains_data(tool):
    case = next(c for c in tool.load_cases() if c["id"] == "untrusted-instructions")
    assert "{{source_url}}" in tool.reference_note(case)
    assert tool.evaluate_case(case, tool.reference_note(case))["passed"]


def test_code_timestamps_are_not_citations(tool):
    case = tool.load_cases()[0]
    note = tool.reference_note(case) + "\n```text\n[99:99-99:99]\n```\n`[88:88-88:88]`"
    assert tool.evaluate_case(case, note)["passed"]


def test_external_notes_are_explicit_and_missing_never_falls_back(tool, tmp_path):
    assert not tool.evaluate_suite(notes_dir=tmp_path)["passed"]
    for case in tool.load_cases():
        (tmp_path / (case["id"] + ".md")).write_text(tool.reference_note(case), encoding="utf-8")
    result = tool.evaluate_suite(notes_dir=tmp_path)
    assert result["passed"] and result["mode"] == "supplied_synthetic_notes_rules_only"
    body = "PRIVATE_SENTINEL_NO_ECHO"
    (tmp_path / (tool.CASE_IDS[0] + ".md")).write_text(body, encoding="utf-8")
    assert body not in json.dumps(tool.evaluate_suite(notes_dir=tmp_path))


def test_fixture_validation_rejects_non_finite_time(tool):
    case = copy.deepcopy(tool.load_cases()[0])
    case["segments"][0]["start"] = float("nan")
    with pytest.raises(ValueError, match="case_invalid"):
        tool.validate_case(case)


def test_fixture_validation_rejects_unknown_template(tool):
    case = copy.deepcopy(tool.load_cases()[0])
    case["template_id"] = "PRIVATE_SENTINEL"
    with pytest.raises(ValueError, match="case_invalid"):
        tool.validate_case(case)


def test_frontmatter_uses_existing_production_template_name(tool):
    import yaml
    case = tool.load_cases()[0]
    metadata = yaml.safe_load(tool.reference_note(case).split("---", 2)[1])
    assert metadata["template"] == tool.TEMPLATES[case["template_id"]].name


@pytest.mark.parametrize("mutation", ["point_type", "extra_segment", "bad_anchor", "boolean_version"])
def test_fixture_schema_validation_is_explicit(tool, mutation):
    case = copy.deepcopy(tool.load_cases()[0])
    if mutation == "point_type":
        case["required_points"][0]["any_of"] = "invalid"
    elif mutation == "extra_segment":
        case["segments"][0]["private"] = "sentinel"
    elif mutation == "bad_anchor":
        case["anchors"][0]["start"] = float("inf")
    else:
        case["schema_version"] = True
    with pytest.raises(ValueError, match="case_invalid"):
        tool.validate_case(case)


def test_long_case_has_real_tail_anchor_not_long_text_claim(tool):
    case = next(c for c in tool.load_cases() if c["id"] == "long-timeline-tail")
    assert case["segments"][-1]["start"] >= 7200
    note = tool.reference_note(case)
    assert tool.evaluate_case(case, note)["passed"]
    assert not tool.evaluate_case(case, note.replace("TAIL-73", "遗漏"))["passed"]


@pytest.mark.parametrize("citation", ["[00:0]", "[00:05-bad]", "[00:10-00:02]", "[01:60:01]"])
def test_malformed_time_tokens_fail(tool, citation):
    case = tool.load_cases()[0]
    assert "timestamp_invalid" in tool.evaluate_case(case, tool.reference_note(case) + citation)["failures"]


def test_reference_images_not_silently_marked_checked(tool):
    case = tool.load_cases()[0]
    result = tool.evaluate_case(case, tool.reference_note(case) + "\n![图][private]\n[private]: /secret.png")
    assert "attachment_unsupported" in result["failures"]


def test_report_reproducible_with_content_identity(tool):
    assert tool.evaluate_suite() == tool.evaluate_suite()
    case = tool.load_cases()[0]
    first = tool.evaluate_case(case, tool.reference_note(case))
    second = tool.evaluate_case(case, tool.reference_note(case) + "\n另一个合法标题")
    assert first["passed"] and second["passed"]
    assert first["note_sha256"] != second["note_sha256"]
    assert first["transcript_sha256"] == second["transcript_sha256"]
