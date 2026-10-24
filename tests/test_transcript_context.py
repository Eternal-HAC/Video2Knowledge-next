"""G3: deterministic, read-only time lookup. All inputs are synthetic."""
import hashlib
import json

import pytest
from local_client import TestClient

from backend import main, transcript
from backend.transcript import TranscriptSegment as Segment


def test_revision_is_stable_for_numeric_representation_but_sensitive_to_content():
    items = [Segment(0, 3, "甲"), Segment(3, 8, "乙")]
    revision = transcript.transcript_revision(items)
    assert revision == transcript.transcript_revision([Segment(0.0, 3.0, "甲"), Segment(3.0, 8.0, "乙")])
    assert len(revision) == 64
    assert revision != transcript.transcript_revision(list(reversed(items)))
    assert revision != transcript.transcript_revision([Segment(0, 4, "甲"), items[1]])
    assert revision != transcript.transcript_revision([Segment(0, 3, "甲改"), items[1]])


@pytest.mark.parametrize("start,end,indices", [
    (2, 7, [0, 1, 2]), (3, None, [1, 2]), (8, None, [3]),
    (8, 8, [3]), (9, None, []), (0, 3, [0]), (7, 8, [1]),
])
def test_lookup_overlaps_without_merging_duplicate_timestamps(start, end, indices):
    items = [Segment(0, 3, "甲"), Segment(3, 8, "乙"), Segment(3, 4, "同时间"), Segment(8, 8, "点")]
    result = transcript.locate_transcript(items, start, end)
    assert [item["index"] for item in result] == indices


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(main, "tasks", {})
    def forbidden(*args, **kwargs):
        pytest.fail("Read-only context must not run a task or media operation")
    monkeypatch.setattr(main, "run_queued_video_task", forbidden)
    monkeypatch.setattr(main, "run_transcription", forbidden)
    monkeypatch.setattr(main.video_processor, "download_audio", forbidden)
    directory = tmp_path / "legacy"
    directory.mkdir()
    (directory / "task.json").write_text(json.dumps({
        "title": "合成旧任务", "source_url": "https://www.bilibili.com/video/BV1234567890",
        "bili_selected_pages": [{"page": 1}, {"page": 2}], "future": "keep",
    }), encoding="utf-8")
    (directory / "notes.md").write_text("# 笔记\n\n观点 [00:02-00:07]", encoding="utf-8")
    (directory / "transcript.json").write_text(json.dumps({
        "source": "bilibili_ai_subtitle", "language": "zh",
        "segments": [
            {"start": 0, "end": 3, "text": "【P1】合成甲"},
            {"start": 3, "end": 8, "text": "【P2】<script>合成乙</script>"},
            {"start": 3, "end": 4, "text": "同时间"},
        ],
    }), encoding="utf-8")
    return directory, TestClient(main.app)


def context(client, **params):
    return client.get("/api/task/legacy/transcript-context", params={"start": 2, **params})


def test_legacy_context_is_paged_read_only_and_explains_multi_page_media(saved):
    directory, client = saved
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    response = context(client, end=7, limit=2)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3 and body["has_more"] is True
    assert [s["index"] for s in body["segments"]] == [0, 1]
    assert body["timeline"] == "merged"
    assert body["media_state"] == "not_retained"
    assert body["note_hash"] == hashlib.sha256((directory / "notes.md").read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    second = context(client, end=7, offset=2, limit=2,
                     transcript_hash=body["transcript_hash"], note_hash=body["note_hash"]).json()
    assert [s["index"] for s in second["segments"]] == [2]
    assert second["has_more"] is False
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before
    assert main.tasks == {}


@pytest.mark.parametrize("params,state", [
    ({"start": 20}, "outside"), ({"start": 0, "end": 20}, "partial"),
    ({"start": 0, "end": 8}, "matched"),
])
def test_context_range_states(saved, params, state):
    _, client = saved
    data = context(client, **params).json()
    assert data["range_state"] == state
    assert data["coverage"] == {"start": 0, "end": 8}


def test_gap_does_not_silently_return_nearest_segment(saved):
    directory, client = saved
    path = directory / "transcript.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["segments"] = [{"start": 0, "end": 1, "text": "首句"}, {"start": 9, "end": 10, "text": "尾句"}]
    path.write_text(json.dumps(payload), encoding="utf-8")
    body = context(client, start=5).json()
    assert body["range_state"] == "gap" and body["segments"] == []


@pytest.mark.parametrize("params", [
    {"start": -1}, {"start": "nan"}, {"end": "inf"}, {"end": 1},
    {"limit": 101}, {"offset": -1}, {"transcript_hash": "oops"}, {"note_hash": "oops"},
])
def test_context_rejects_invalid_parameters(saved, params):
    _, client = saved
    assert context(client, **params).status_code == 422


@pytest.mark.parametrize("filename", ["notes.md", "transcript.json"])
def test_changed_file_invalidates_old_mapping(saved, filename):
    directory, client = saved
    first = context(client).json()
    path = directory / filename
    if filename.endswith("json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["segments"][0]["text"] += "修改"
        text = json.dumps(data)
    else:
        text = "# 新笔记"
    path.write_text(text, encoding="utf-8")
    response = context(client, note_hash=first["note_hash"], transcript_hash=first["transcript_hash"])
    assert response.status_code == 409
    assert "变化" in response.json()["detail"]
    assert str(directory) not in response.text


@pytest.mark.parametrize("payload", [None, "broken", "[]", '{"segments": []}',
    '{"segments": [{"start":0,"end":9,"text":"ok"}, {"text":"bad"}]}'])
def test_missing_or_corrupt_transcript_is_fixed_error(saved, payload):
    directory, client = saved
    path = directory / "transcript.json"
    if payload is None:
        path.unlink()
    else:
        path.write_text(payload, encoding="utf-8")
    response = context(client)
    assert response.status_code == 409
    assert str(directory) not in response.text
    assert "转录" in response.json()["detail"]


def test_media_presence_and_single_timeline_are_observed_without_opening_media(saved):
    directory, client = saved
    (directory / "audio.wav").write_bytes(b"synthetic-not-a-real-wave")
    (directory / "task.json").write_text("{}", encoding="utf-8")
    data = context(client).json()
    assert data["media_state"] == "retained"
    # Old manifests may lack page metadata; content markers still warn against source seeking.
    assert data["timeline"] == "merged"


def test_context_does_not_follow_unsafe_paths(saved, monkeypatch):
    _, client = saved
    monkeypatch.setattr(main, "_plain_path_snapshot", lambda *args, **kwargs: None)
    assert context(client).status_code == 409


def test_missing_note_with_expected_revision_does_not_claim_mapping(saved):
    directory, client = saved
    (directory / "notes.md").unlink()
    assert context(client, note_hash="0" * 64).status_code == 409
    # Transcript-only tasks can still be inspected without a note hash.
    assert context(client).status_code == 200


def test_explicit_history_refresh_reads_current_note_without_mutating_cached_result(saved):
    directory, client = saved
    main.tasks["legacy"] = {"status": "completed", "output": "note", "result": {"markdown": "# 缓存旧笔记"}}
    note = directory / "notes.md"
    note.write_text("# 外部修改的新笔记 [00:03]", encoding="utf-8")
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    fresh = client.get("/api/task/legacy?refresh_note=true").json()
    assert fresh["result"]["markdown"] == note.read_text(encoding="utf-8")
    assert client.get("/api/task/legacy").json()["result"]["markdown"] == "# 缓存旧笔记"
    revision = hashlib.sha256(fresh["result"]["markdown"].encode("utf-8")).hexdigest()
    assert context(client, note_hash=revision).status_code == 200
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before


def test_explicit_note_refresh_fails_closed_when_current_file_is_gone(saved):
    directory, client = saved
    main.tasks["legacy"] = {"status": "completed", "output": "note", "result": {"markdown": "# 缓存旧笔记"}}
    (directory / "notes.md").unlink()
    response = client.get("/api/task/legacy?refresh_note=true")
    assert response.status_code == 409
    assert "缓存旧笔记" not in response.text
    assert str(directory) not in response.text
