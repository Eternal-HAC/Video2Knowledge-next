import asyncio
import hashlib
import json

import pytest
from fastapi import HTTPException
from local_client import TestClient

from backend import main
from backend.config_store import ConfigStore


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(main, "tasks", {})
    monkeypatch.setattr(main, "running_jobs", {})
    monkeypatch.setattr(main, "config_store", ConfigStore(tmp_path))
    async def no_background_side_effects(*args):
        pass
    monkeypatch.setattr(main, "run_queued_video_task", no_background_side_effects)
    return tmp_path


def old_task(workspace, task_id="old", *, source="https://example.org/video", subtitle=False):
    directory = workspace / task_id
    directory.mkdir()
    (directory / "task.json").write_text(json.dumps({
        "task_id": task_id, "source_url": source, "output": "note", "favorite": True,
        "origin": "agent", "future": {"kept": True}, "subtitle_import": subtitle,
        "uploaded_filename": "合成字幕.srt" if subtitle else None,
        "runtime": {"status": "failed"},
    }), encoding="utf-8")
    (directory / "transcript.json").write_text(json.dumps({
        "source": "subtitle_import" if subtitle else "platform_subtitle", "language": "zh",
        "segments": [{"start": 0, "end": 12, "text": "这是一段足够清晰的合成转录内容，用来验证失败后的安全恢复。"}],
    }), encoding="utf-8")
    return directory


def request(**kwargs):
    return main.SummarizeRequest(llm_config=main.LLMConfig(api_key="synthetic-key"), **kwargs)


@pytest.mark.parametrize("payload", [
    [], {"segments": [None]}, {"segments": [{"start": -1, "end": 2, "text": "a"}]},
    {"segments": [{"start": 2, "end": 1, "text": "a"}]},
    {"segments": [{"start": 0, "end": float("nan"), "text": "a"}]},
    {"segments": [{"start": True, "end": 2, "text": "a"}]},
    {"segments": [{"start": 0, "end": 2, "text": {"unexpected": "object"}}]},
    {"segments": [{"start": 0, "end": 2, "text": "valid"}, {"start": "bad", "end": 3, "text": "bad"}]},
    {"source": {}, "segments": [{"start": 0, "end": 2, "text": "valid"}]},
    {"language": [], "segments": [{"start": 0, "end": 2, "text": "valid"}]},
])
def test_reuse_rejects_entire_malformed_transcript(workspace, payload):
    directory = old_task(workspace)
    (directory / "transcript.json").write_text(json.dumps(payload), encoding="utf-8")
    assert main.load_transcript_result(directory) is None
    assert main.find_reusable_task("https://example.org/video") is None


@pytest.mark.asyncio
async def test_explicit_resume_refuses_missing_transcript_before_new_task(workspace):
    directory = old_task(workspace)
    (directory / "transcript.json").unlink()
    with pytest.raises(HTTPException) as error:
        await main.submit_video_task(request(resume_task_id="old"), "web")
    assert error.value.status_code == 409
    assert main.tasks == {}
    assert list(workspace.iterdir()) == [directory]


@pytest.mark.asyncio
async def test_explicit_resume_rejects_conflicting_source(workspace):
    old_task(workspace)
    with pytest.raises(HTTPException) as error:
        await main.submit_video_task(request(
            resume_task_id="old", video_url="https://example.org/different-video"
        ), "web")
    assert error.value.status_code == 409
    assert main.tasks == {}


def test_submission_lookup_is_read_only(workspace, monkeypatch):
    directory = old_task(workspace)
    main._merge_task_manifest("old", "submission", {
        "client_request_id": "uncertain-17", "fingerprint": "synthetic"
    })
    before = (directory / "task.json").read_bytes()
    with TestClient(main.app) as client:
        found = client.get("/api/submission/uncertain-17")
        assert found.status_code == 200
        assert found.json()["task_id"] == "old"
        assert client.get("/api/submission/missing").status_code == 404
        assert client.get("/api/submission/bad.id").status_code == 422
    assert (directory / "task.json").read_bytes() == before
    assert main.running_jobs == {}


@pytest.mark.asyncio
async def test_http_and_in_process_mcp_share_recovery_payload(workspace):
    from backend.mcp_server import InProcessBackend
    old_task(workspace)
    direct = await InProcessBackend().get_task("old")
    with TestClient(main.app) as client:
        response = client.get("/api/task/old")
    assert response.status_code == 200
    assert direct["recovery"] == response.json()["recovery"]
    assert direct["recovery"]["can_resume"] is True


@pytest.mark.asyncio
async def test_resume_preserves_parent_identity_and_old_favorite(workspace, monkeypatch):
    directory = old_task(workspace, source=None, subtitle=True)
    original = (directory / "task.json").read_bytes()
    async def queued(*args):
        pass
    monkeypatch.setattr(main, "run_queued_video_task", queued)
    result = await main.submit_video_task(request(resume_task_id="old"), "web")
    await asyncio.sleep(0)
    manifest = main.read_task_manifest(result["task_id"])
    assert manifest["parent_task_id"] == "old"
    assert manifest["transcript_ref"] == {"task_id": "old", "filename": "transcript.json"}
    assert manifest["subtitle_import"] is True
    assert manifest["uploaded_filename"] == "合成字幕.srt"
    assert (directory / "task.json").read_bytes() == original


@pytest.mark.asyncio
async def test_replay_same_id_survives_restart_and_excludes_secrets(workspace, monkeypatch):
    called = []
    async def queued(task_id, req):
        called.append(task_id)
        main.tasks[task_id]["status"] = "failed"
        main.persist_task_runtime(task_id)
    monkeypatch.setattr(main, "run_queued_video_task", queued)
    def build(key):
        return main.SummarizeRequest(
            video_url="https://example.org/video", client_request_id="request-17",
            llm_config=main.LLMConfig(api_key=key),
        )
    first, second = await asyncio.gather(
        main.submit_video_task(build("first-secret"), "web"),
        main.submit_video_task(build("second-secret"), "web"),
    )
    await asyncio.sleep(0)
    assert first["task_id"] == second["task_id"]
    assert len(called) == 1
    blob = (workspace / first["task_id"] / "task.json").read_text("utf-8")
    for secret in ["first-secret", "second-secret"]:
        assert secret not in blob
        assert hashlib.sha256(secret.encode()).hexdigest() not in blob
    main.tasks.clear()  # simulate in-memory state loss, persisted mapping remains
    third = await main.submit_video_task(build("new-key-after-restart"), "web")
    assert third["task_id"] == first["task_id"]
    assert third["replayed"] is True
    assert len(called) == 1
    with pytest.raises(HTTPException) as error:
        changed = build("not-in-fingerprint")
        changed.summary_style = "faithful"
        await main.submit_video_task(changed, "web")
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_upload_replay_checked_before_consumed_upload_validation(workspace, monkeypatch):
    directory = old_task(workspace, "upload", source=None, subtitle=True)
    main.tasks["upload"] = main.new_task("uploaded", "upload")
    main.tasks["upload"].update(subtitle_import=True, uploaded_filename="合成字幕.srt")
    async def queued(*args):
        pass
    monkeypatch.setattr(main, "run_queued_video_task", queued)
    kwargs = {"upload_task_id": "upload", "client_request_id": "upload-submit"}
    first = await main.submit_video_task(request(**kwargs), "web")
    second = await main.submit_video_task(request(**kwargs), "web")
    await asyncio.sleep(0)
    assert first["task_id"] == second["task_id"] == "upload"
    assert main.read_task_manifest("upload")["future"] == {"kept": True}


def test_cancelled_progress_and_persistence_cannot_regress(workspace):
    old_task(workspace)
    task = main.new_task("cancelled", "old")
    task.update(step=4, step_name="已取消", progress=50)
    main.tasks["old"] = task
    main.persist_task_runtime("old")
    main.set_progress(task, 6, "迟到回调", 90, "迟到")
    assert task["step_name"] == "已取消"
    task["status"] = "processing"  # delayed external snapshot
    main.persist_task_runtime("old")
    assert main.read_task_manifest("old")["runtime"]["status"] == "cancelled"


def test_runtime_unknown_fields_survive_progress_save(workspace):
    old_task(workspace)
    main._merge_task_manifest("old", "runtime", {"future_runtime": {"version": 10}})
    main.tasks["old"] = main.new_task("processing", "old")
    main.persist_task_runtime("old")
    assert main.read_task_manifest("old")["runtime"]["future_runtime"] == {"version": 10}


def test_transcript_task_with_corrupt_artifact_is_not_restored_completed(workspace):
    directory = old_task(workspace)
    main._merge_task_manifest("old", "output", "transcript")
    (directory / "transcript.json").write_text("{broken", encoding="utf-8")
    restored = main.restore_task_on_demand("old")
    assert restored["status"] == "failed"


def test_request_fingerprint_ignores_cookie_and_key_values(workspace):
    first = request(video_url="https://example.org/video")
    second = request(video_url="https://example.org/video")
    second.llm_config.api_key = "different-secret"
    second.bilibili_cookie = main.BilibiliCookie(sessdata="never-hash-this")
    assert main.submission_fingerprint(first, "web") == main.submission_fingerprint(second, "web")


def test_recovery_summary_does_not_read_keys_and_handles_corruption(workspace):
    directory = old_task(workspace)
    task = main.new_task("failed", "old")
    main.tasks["old"] = task
    recovery = main.task_status_payload("old", task)["recovery"]
    assert recovery["can_resume"] is True
    assert recovery["retained"] == ["transcript"]
    assert recovery["redo"] == ["note_generation"]
    (directory / "transcript.json").write_text("{broken", encoding="utf-8")
    recovery = main.task_status_payload("old", task)["recovery"]
    assert recovery["can_resume"] is False
    assert recovery["retained"] == []


@pytest.mark.asyncio
async def test_llm_failure_resume_never_redownloads_or_retranscribes(workspace, monkeypatch):
    directory = old_task(workspace)
    calls = {"download": 0, "asr": 0, "llm": 0}
    async def forbidden_download(*args, **kwargs):
        calls["download"] += 1
        raise AssertionError("unexpected source processing")
    async def forbidden_asr(*args, **kwargs):
        calls["asr"] += 1
        raise AssertionError("unexpected ASR")
    monkeypatch.setattr(main.video_processor, "get_video_info", forbidden_download)
    monkeypatch.setattr(main.video_processor, "fetch_subtitles", forbidden_download)
    monkeypatch.setattr(main.video_processor, "download_audio", forbidden_download)
    monkeypatch.setattr(main.transcriber, "transcribe", forbidden_asr)
    class FakeSummarizer:
        def __init__(self, **kwargs):
            pass
        def describe_effort(self, *args, **kwargs):
            return "synthetic"
        async def generate_summary(self, *args, **kwargs):
            calls["llm"] += 1
            if calls["llm"] == 1:
                raise RuntimeError("synthetic provider failure")
            return "# 恢复后的合成笔记\n\n保留转录，无额外下载。"
    monkeypatch.setattr(main, "LLMSummarizer", FakeSummarizer)
    async def run(task_id, req):
        await main.process_video_task(task_id, req)
    monkeypatch.setattr(main, "run_queued_video_task", run)
    first = await main.submit_video_task(request(resume_task_id="old"), "web")
    await main.running_jobs[first["task_id"]]
    assert main.tasks[first["task_id"]]["status"] == "failed"
    second = await main.submit_video_task(request(resume_task_id=first["task_id"]), "web")
    await main.running_jobs[second["task_id"]]
    assert main.tasks[second["task_id"]]["status"] == "completed"
    assert calls == {"download": 0, "asr": 0, "llm": 2}
    assert main.read_task_manifest(second["task_id"])["source_url"] == "https://example.org/video"
    assert main.read_task_manifest("old")["favorite"] is True
    assert (directory / "transcript.json").is_file()


@pytest.mark.asyncio
async def test_source_deleted_after_submit_fails_closed(workspace, monkeypatch):
    directory = old_task(workspace)
    async def queued(*args):
        pass
    async def forbidden(*args, **kwargs):
        raise AssertionError("must never reach source processing")
    monkeypatch.setattr(main, "run_queued_video_task", queued)
    monkeypatch.setattr(main.video_processor, "get_video_info", forbidden)
    result = await main.submit_video_task(request(resume_task_id="old"), "web")
    await asyncio.sleep(0)
    (directory / "transcript.json").unlink()
    await main.process_video_task(result["task_id"], request(resume_task_id="old"))
    task = main.tasks[result["task_id"]]
    assert task["status"] == "failed"
    assert "未执行下载或 ASR" in task["error"]


def test_http_transcribe_idempotency_and_validation(workspace, monkeypatch):
    called = []
    async def queued(task_id, req):
        called.append(task_id)
    monkeypatch.setattr(main, "run_queued_video_task", queued)
    with TestClient(main.app) as client:
        data = {"video_url": "https://example.org/video", "client_request_id": "http-transcript"}
        first = client.post("/api/transcribe", json=data)
        second = client.post("/api/transcribe", json=data)
        assert first.status_code == second.status_code == 200
        assert first.json()["task_id"] == second.json()["task_id"]
        assert second.json()["replayed"] is True
        assert len(called) == 1
        assert client.post("/api/transcribe", json={**data, "use_gpu": True}).status_code == 409
        assert client.post("/api/transcribe", json={**data, "client_request_id": "../bad"}).status_code == 422


def test_runtime_favorite_publication_merges_do_not_lose_fields(workspace):
    from concurrent.futures import ThreadPoolExecutor
    old_task(workspace)
    main.tasks["old"] = main.new_task("completed", "old")
    def update(i):
        if i % 3 == 0:
            main.persist_task_runtime("old")
        elif i % 3 == 1:
            main._merge_task_manifest("old", "favorite", True)
        else:
            main._merge_task_manifest("old", "feishu_publication", {"status": "failed"})
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(update, range(60)))
    manifest = main.read_task_manifest("old")
    assert manifest["runtime"]["status"] == "completed"
    assert manifest["favorite"] is True
    assert manifest["feishu_publication"] == {"status": "failed"}
    assert manifest["future"] == {"kept": True}
