"""Offline progress contracts: no model, media, provider or credential access."""
import asyncio
import json
import math
from pathlib import Path

import pytest

from backend import main
from backend.transcript import TranscriptSegment
from backend.video_processor import BiliPage, BiliSubtitleOutcome, SubtitleResult, VideoProcessor


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), -float("inf"), None, "invalid"])
def test_unknown_duration_has_no_percent_or_eta(value):
    result = main.asr_progress_snapshot(position=20, duration=value, elapsed=10)
    assert result["phase_progress"] is None
    assert result["estimated_remaining_seconds"] is None
    assert result["total_seconds"] == 0
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("field", ["position", "elapsed", "offset_seconds", "overall_duration"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), "invalid"])
def test_snapshot_invalid_numbers_are_json_safe(field, value):
    args = dict(position=20, duration=100, elapsed=10, offset_seconds=0, overall_duration=None)
    args[field] = value
    snapshot = main.asr_progress_snapshot(**args)
    json.dumps(snapshot, allow_nan=False)
    assert all(not isinstance(v, float) or math.isfinite(v) for v in snapshot.values())


def test_unknown_multipage_total_does_not_use_current_page_percent():
    result = main.asr_progress_snapshot(
        position=30, duration=30, elapsed=20, offset_seconds=50,
        overall_duration=None, aggregate=True,
    )
    assert result["processed_seconds"] == 80
    assert result["total_seconds"] == 0
    assert result["phase_progress"] is None
    assert result["estimated_remaining_seconds"] is None
    assert result["overall_progress"] == 28


@pytest.mark.asyncio
async def test_reporter_ignores_duplicate_reverse_and_invalid_events():
    task = main.new_task("processing")
    task.update(step=4, progress=28)
    reporter = main.transcribe_progress_reporter(task, "small")
    reporter(40, 100)
    await asyncio.sleep(0)
    before = dict(task)
    before["logs"] = list(task["logs"])
    for position in (40, 30, -1, float("nan"), float("inf")):
        reporter(position, 100)
    await asyncio.sleep(0)
    assert task == before


@pytest.mark.asyncio
@pytest.mark.parametrize("transition", ["next-page", "download", "summarize", "cancel", "completed", "failed", "cancelled", "queued"])
async def test_reporter_cannot_mutate_after_stage_or_lifecycle_change(transition):
    task = main.new_task("processing")
    main.set_progress(task, 4, "语音转写", 28, "start")
    old = main.transcribe_progress_reporter(task, "small")
    old(20, 100)
    await asyncio.sleep(0)
    if transition == "next-page":
        main.set_progress(task, 4, "语音转写", 35, "next")
        main.transcribe_progress_reporter(task, "small", offset_seconds=100, overall_duration=200)
    elif transition in {"download", "summarize"}:
        main.set_progress(task, 3 if transition == "download" else 5, transition, 40, transition)
    elif transition == "cancel":
        task["_cancel_requested"] = True
    else:
        task["status"] = transition
    before = dict(task)
    before["logs"] = list(task["logs"])
    old(90, 100)
    await asyncio.sleep(0)
    assert task == before


@pytest.mark.asyncio
async def test_cancel_clears_eta_immediately(monkeypatch):
    task = main.new_task("processing")
    task.update(step=4, phase_progress=50, processed_seconds=50, total_seconds=100, estimated_remaining_seconds=40)
    monkeypatch.setattr(main, "tasks", {"cancel-progress": task})
    monkeypatch.setattr(main, "persist_task_runtime", lambda *_: None)
    await main.cancel_task("cancel-progress")
    assert task["estimated_remaining_seconds"] is None
    assert task["phase_progress"] is None


@pytest.mark.asyncio
async def test_paraformer_has_no_measured_callback(monkeypatch):
    async def fake(*args, **kwargs):
        assert "progress_callback" not in kwargs
        return {"segments": []}
    monkeypatch.setattr(main.paraformer_transcriber, "transcribe", fake)
    await main.run_transcription_local(Path("synthetic.wav"), "paraformer-zh", False, None, None,
                                       lambda *_: pytest.fail("Paraformer must not emit measured progress"))


@pytest.mark.asyncio
@pytest.mark.parametrize("unknown_duration", [False, True])
async def test_mixed_subtitle_multipage_pipeline_progress_never_regresses(tmp_path, monkeypatch, unknown_duration):
    processor = VideoProcessor(tmp_path)
    pages = (
        BiliPage(page=1, part="字幕页", cid=101, duration=60),
        BiliPage(page=2, part="转录页A", cid=102, duration=50),
        BiliPage(page=3, part="转录页B", cid=103, duration=0 if unknown_duration else 50),
    )
    subtitle = SubtitleResult([TranscriptSegment(0, 5, "合成字幕")], "zh", "bilibili_ai_subtitle")
    async def info(*args, **kwargs):
        return {"title": "合成多页测试", "source": "bilibili", "duration": 160, "owner": "synthetic"}
    async def subtitles(*args, **kwargs):
        return BiliSubtitleOutcome(subtitle, "partial", pages=pages, total_pages=3,
                                   subtitle_by_page=((1, subtitle),), pages_to_transcribe=pages[1:])
    async def download(*args, **kwargs):
        return tmp_path / "synthetic.wav"
    seen = []
    original = main.set_progress
    def record(task, *args, **kwargs):
        original(task, *args, **kwargs)
        seen.append(dict(task))
    async def transcribe(*args, progress_callback=None, **kwargs):
        progress_callback(40, 50)
        await asyncio.sleep(0)
        progress_callback(50, 50)
        await asyncio.sleep(0)
        return {"segments": [TranscriptSegment(0, 50, "合成转录")], "language": "zh",
                "duration": 50, "device": "cpu", "model": "small", "requested_model": "small"}
    monkeypatch.setattr(processor, "get_video_info", info)
    monkeypatch.setattr(processor, "fetch_bilibili_subtitles", subtitles)
    monkeypatch.setattr(processor, "download_audio", download)
    monkeypatch.setattr(main, "video_processor", processor)
    monkeypatch.setattr(main, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(main, "run_transcription", transcribe)
    monkeypatch.setattr(main, "set_progress", record)
    task_id = "synthetic-multipage"
    (tmp_path / task_id).mkdir()
    monkeypatch.setattr(main, "tasks", {task_id: main.new_task()})
    request = main.SummarizeRequest(video_url="https://www.bilibili.com/video/BV1xx",
                                    output="transcript", whisper_model="small",
                                    llm_config=main.LLMConfig(model_type="deepseek", api_key=""))
    await main.process_video_task(task_id, request)
    task = main.tasks[task_id]
    assert task["status"] == "completed", task.get("error")
    progress = [s["progress"] for s in seen]
    assert progress == sorted(progress)
    measured = [s for s in seen if s.get("processed_seconds") is not None]
    assert measured and measured[-1]["processed_seconds"] == 100
    assert all(s["total_seconds"] == (0 if unknown_duration else 100) for s in measured)
    if unknown_duration:
        assert all(s["phase_progress"] is None and s["estimated_remaining_seconds"] is None for s in measured)
    assert task["estimated_remaining_seconds"] is None
