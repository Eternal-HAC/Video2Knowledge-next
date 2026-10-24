"""Deterministic rules on synthetic cases only; never calls a summarizer."""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path, PurePosixPath

import yaml

from backend.note_templates import _builtin_templates, render_note
from backend.transcript import TranscriptSegment, locate_transcript, parse_subtitle_payload, segments_to_srt, transcript_revision
from scripts.quality_io import SafeArgumentParser, read_text, write_report

CASE_IDS = ("concept-lecture", "tutorial-steps", "interview-views", "negation-boundary", "number-units", "formula-meaning", "code-example", "repeated-speech", "bilingual-terms", "subtitle-gap", "long-timeline-tail", "untrusted-instructions")
FIXTURES = Path(__file__).absolute().parents[1] / "tests" / "fixtures" / "note_quality"
TEMPLATES = {t.id: t for t in _builtin_templates()}
CITATION_RE = re.compile(r"\[(\d{1,4}:\d{2}(?::\d{2})?)(?:-(\d{1,4}:\d{2}(?::\d{2})?))?\]")


def validate_case(case: dict) -> None:
    def require(condition):
        if not condition:
            raise ValueError("case_invalid")

    try:
        require(type(case) is dict)
        require(type(case["schema_version"]) is int and case["schema_version"] == 1 and case["id"] in CASE_IDS)
        require(case["template_id"] in TEMPLATES)
        require(isinstance(case["reference_body"], str) and 0 < len(case["reference_body"]) <= 100000)
        points = case["required_points"]
        require(type(points) is list and 3 <= len(points) <= 8)
        require(len({p["id"] for p in points}) == len(points))
        for point in points:
            require(re.fullmatch(r"P[0-9]{2}", point["id"]))
            require(type(point["any_of"]) is list and 1 <= len(point["any_of"]) <= 8)
            require(all(type(t) is str and 0 < len(t) < 1000 for t in point["any_of"]))
        segments = case["segments"]
        require(type(segments) is list and 1 <= len(segments) <= 100)
        for segment in segments:
            require(type(segment) is dict and set(segment) == {"start", "end", "text"})
            for key in ("start", "end"):
                require(type(segment[key]) in (int, float) and 0 <= segment[key] < 604800 and math.isfinite(segment[key]))
            require(segment["end"] >= segment["start"])
            require(type(segment["text"]) is str and 0 < len(segment["text"]) < 10000)
        for key in ("required_literals", "forbidden_literals", "available_attachments"):
            require(type(case[key]) is list and len(case[key]) <= 30)
            require(all(type(t) is str and 0 < len(t) < 1000 for t in case[key]))
        require(type(case["anchors"]) is list and 1 <= len(case["anchors"]) <= 100)
        for anchor in case["anchors"]:
            require(all(type(anchor[k]) in (int, float) and 0 <= anchor[k] < 604800 and math.isfinite(anchor[k]) for k in ("start", "end")))
            require(anchor["end"] >= anchor["start"])
            require(type(anchor["indices"]) is list and anchor["indices"] and all(type(i) is int and 0 <= i < len(segments) for i in anchor["indices"]))
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError("case_invalid") from None


def load_cases() -> list[dict]:
    cases = []
    for case_id in CASE_IDS:
        try:
            case = json.loads(read_text(FIXTURES / (case_id + ".json")))
            validate_case(case)
            if case["id"] != case_id:
                raise ValueError("case_invalid")
        except (ValueError, TypeError):
            raise ValueError("case_invalid") from None
        cases.append(case)
    return cases


def reference_note(case: dict) -> str:
    validate_case(case)
    return render_note(TEMPLATES[case["template_id"]].layout,
                       {"title": "合成评测示例", "platform": "local", "template": TEMPLATES[case["template_id"]].name,
                        "transcript_source": "subtitle_import"}, case["reference_body"])


def _clock(value: str) -> int:
    pieces = [int(v) for v in value.split(":")]
    if pieces[-1] >= 60 or (len(pieces) == 3 and pieces[1] >= 60):
        raise ValueError("timestamp_invalid")
    if len(pieces) == 2:
        return pieces[0] * 60 + pieces[1]
    return pieces[0] * 3600 + pieces[1] * 60 + pieces[2]


def _attachment_safe(value: str) -> bool:
    value = value.removeprefix("./")
    parts = PurePosixPath(value).parts
    return bool(parts) and not value.startswith("/") and not any(x in value for x in ("\\", ":", "%", "?", "#", "<", ">")) and all(p not in ("..", ".") for p in parts)


def evaluate_case(case: dict, note: str) -> dict:
    validate_case(case)
    failures = []
    body, metadata = note, None
    fm = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", note, re.S)
    if fm:
        try:
            metadata = yaml.safe_load(fm[1])
        except (yaml.YAMLError, ValueError, RecursionError):
            pass
        body = note[fm.end():]
    if type(metadata) is not dict:
        failures.append("frontmatter_invalid")
    elif any(metadata.get(k) != v for k, v in {"platform": "local", "template": TEMPLATES[case["template_id"]].name, "transcript_source": "subtitle_import"}.items()):
        failures.append("frontmatter_metadata")
    if not body.strip():
        failures.append("body_empty")
    covered = sum(any(literal in body for literal in p["any_of"]) for p in case["required_points"])
    if covered != len(case["required_points"]):
        failures.append("missing_point")
    if any(t not in body for t in case["required_literals"]):
        failures.append("missing_literal")
    if any(t in body for t in case["forbidden_literals"]):
        failures.append("forbidden_literal")
    segments = [TranscriptSegment(**s) for s in case["segments"]]
    # Limited Markdown recognizer: do not mistake code examples for citations.
    visible = re.sub(r"(`{3,}|~{3,})[^\n]*\n.*?\1", "", body, flags=re.S)
    visible = re.sub(r"`+[^`\n]*`+", "", visible)
    citations = []
    for token in re.findall(r"\[\d+:[^\]\n]*\]", visible):
        match = CITATION_RE.fullmatch(token)
        if match is None:
            failures.append("timestamp_invalid")
            continue
        try:
            start = _clock(match[1])
            end = _clock(match[2]) if match[2] else start
            if end < start:
                raise ValueError("timestamp_invalid")
        except ValueError:
            failures.append("timestamp_invalid")
            continue
        indices = [m["index"] for m in locate_transcript(segments, start, end)]
        if not indices:
            failures.append("timestamp_unmapped")
        citations.append((start, end, indices))
    for anchor in case["anchors"]:
        # A range may vary, but it must overlap exactly the annotated segments.
        if not any(indices == anchor["indices"] for _, _, indices in citations):
            failures.append("timestamp_missing")
        actual = [m["index"] for m in locate_transcript(segments, anchor["start"], anchor["end"])]
        if actual != anchor["indices"]:
            failures.append("fixture_mapping_invalid")
    attachments = re.findall(r"!\[[^\]]*\]\(([^)\n]*)\)", visible)
    # Reference-style and incomplete image syntax are outside this evaluator's
    # declared subset. Fail closed rather than silently marking them checked.
    if len(re.findall(r"!\[", visible)) != len(attachments):
        failures.append("attachment_unsupported")
    if re.search(r"<\s*(?:img|picture|source)\b", visible, re.I):
        failures.append("attachment_unsafe")
    for attachment in attachments:
        if not _attachment_safe(attachment):
            failures.append("attachment_unsafe")
        elif attachment.removeprefix("./") not in case["available_attachments"]:
            failures.append("attachment_undeclared")
    roundtrip = parse_subtitle_payload(segments_to_srt(segments), ".srt")
    if roundtrip != segments:
        failures.append("srt_roundtrip")
    return {"case_id": case["id"], "passed": not failures, "failures": sorted(set(failures)),
            "required_points": len(case["required_points"]), "literal_points_present": covered,
            "citation_count": len(citations), "transcript_sha256": transcript_revision(segments),
            "note_sha256": hashlib.sha256(note.encode("utf-8")).hexdigest(),
            "case_sha256": hashlib.sha256(json.dumps(case, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()}


def evaluate_suite(notes_dir: Path | None = None) -> dict:
    results = []
    for case in load_cases():
        try:
            note = reference_note(case) if notes_dir is None else read_text(notes_dir / (case["id"] + ".md"))
            results.append(evaluate_case(case, note))
        except (ValueError, OSError):
            results.append({"case_id": case["id"], "passed": False, "failures": ["note_unavailable"]})
    return {"schema_version": 1, "mode": "reference_rules_only" if notes_dir is None else "supplied_synthetic_notes_rules_only",
            "case_count": len(results), "passed": all(r["passed"] for r in results), "cases": results,
            "manual_review": "not_scored"}


def main(argv=None) -> int:
    parser = SafeArgumentParser(description=__doc__)
    parser.add_argument("--notes-dir", type=Path, help="Only explicitly supplied synthetic case notes")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = evaluate_suite(args.notes_dir)
    except ValueError:
        result = {"passed": False, "error_code": "case_invalid"}
    try:
        write_report(result, args.output)
    except ValueError:
        write_report({"passed": False, "error_code": "output_unavailable"})
        return 2
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
