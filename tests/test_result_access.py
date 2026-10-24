"""Result opening must never turn a manifest into an arbitrary shell target."""
import json
import os
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from local_client import TestClient

from backend import main


@pytest.fixture
def result_case(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    directory = workspace / "safe-result"
    directory.mkdir(parents=True)
    internal = directory / "notes.md"
    internal.write_text("# synthetic", encoding="utf-8")
    destination = tmp_path / "destination"
    destination.mkdir()
    manifest = directory / "task.json"
    manifest.write_text(json.dumps({"output": "note", "note_destination": str(destination)}), encoding="utf-8")
    task = main.new_task("completed")
    task.update(output="note", result={})
    opened = []
    monkeypatch.setattr(main, "WORKSPACE_DIR", workspace)
    monkeypatch.setattr(main, "tasks", {"safe-result": task})
    monkeypatch.setattr(main, "_open_in_file_manager", lambda p: opened.append(p) or True)
    return SimpleNamespace(
        workspace=workspace, directory=directory, internal=internal,
        destination=destination, manifest=manifest, task=task, opened=opened,
        client=TestClient(main.app),
    )


def open_result(case, target="file"):
    return case.client.post("/api/task/safe-result/open-result", json={"target": target})


@pytest.mark.parametrize("name", ["notes.exe", "notes.lnk", "notes.url", "notes.md.exe", "notes.html"])
@pytest.mark.parametrize("target", ["file", "folder"])
def test_open_result_rejects_non_markdown_archive(result_case, name, target):
    case = result_case
    candidate = case.destination / name
    candidate.write_text("synthetic, never execute", encoding="utf-8")
    case.task["result"]["archived_path"] = str(candidate)
    assert open_result(case, target).status_code == 200
    assert case.opened == [case.internal if target == "file" else case.directory]


@pytest.mark.parametrize("raw_root", ["bad\u0000root", {"path": "bad"}, ["bad"], 42])
def test_open_result_malformed_destination_falls_back(result_case, raw_root):
    case = result_case
    candidate = case.destination / "note.md"
    candidate.write_text("synthetic", encoding="utf-8")
    case.task["result"]["archived_path"] = str(candidate)
    case.manifest.write_text(json.dumps({"note_destination": raw_root}), encoding="utf-8")
    assert open_result(case).status_code == 200
    assert case.opened == [case.internal]


@pytest.mark.parametrize("payload", ["{broken", "[]", "null", '"string"'])
def test_open_result_malformed_manifest_is_safe(result_case, payload):
    case = result_case
    case.manifest.write_text(payload, encoding="utf-8")
    assert open_result(case).status_code == 200
    assert case.opened == [case.internal]


def test_open_result_rejects_hardlinked_files(result_case):
    case = result_case
    candidate = case.destination / "linked.md"
    os.link(case.internal, candidate)
    case.task["result"]["archived_path"] = str(candidate)
    response = open_result(case)
    assert response.status_code == 404
    assert response.json()["detail"] == "结果文件不存在或路径不可安全打开"
    assert case.opened == []


@pytest.mark.parametrize("component", ["file", "parent", "ancestor"])
def test_open_result_rejects_reparse_components_before_resolve(result_case, monkeypatch, component):
    case = result_case
    ancestor = case.destination / "ancestor"
    parent = ancestor / "parent"
    parent.mkdir(parents=True)
    candidate = parent / "note.md"
    candidate.write_text("synthetic", encoding="utf-8")
    case.manifest.write_text(json.dumps({"note_destination": str(parent)}), encoding="utf-8")
    case.task["result"]["archived_path"] = str(candidate)
    blocked = {"file": candidate, "parent": parent, "ancestor": ancestor}[component]
    original = Path.stat

    def fake_stat(path, *, follow_symlinks=True):
        info = original(path, follow_symlinks=follow_symlinks)
        if path == blocked and not follow_symlinks:
            fields = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
            fields["st_file_attributes"] = 0x400
            return SimpleNamespace(**fields)
        return info

    monkeypatch.setattr(Path, "stat", fake_stat)
    assert open_result(case).status_code == 200
    assert case.opened == [case.internal]


def test_open_result_real_directory_link_is_not_followed(result_case):
    case = result_case
    alias = case.workspace.parent / "junction"
    if os.name == "nt":
        # Junction creation does not require the symlink privilege. Exact test paths only.
        command = f"New-Item -ItemType Junction -Path '{alias}' -Target '{case.destination}' | Out-Null"
        subprocess.run(["powershell", "-NoProfile", "-Command", command], check=True, capture_output=True)
    else:
        alias.symlink_to(case.destination, target_is_directory=True)
    try:
        (case.destination / "note.md").write_text("synthetic", encoding="utf-8")
        case.task["result"]["archived_path"] = str(alias / "note.md")
        case.manifest.write_text(json.dumps({"note_destination": str(alias)}), encoding="utf-8")
        assert open_result(case).status_code == 200
        assert case.opened == [case.internal]
    finally:
        if os.name == "nt":
            alias.rmdir()  # removes the junction itself, never its target
        else:
            alias.unlink()


def test_open_result_internal_reparse_file_is_rejected(result_case, monkeypatch):
    case = result_case
    original = Path.stat

    def fake_stat(path, *, follow_symlinks=True):
        info = original(path, follow_symlinks=follow_symlinks)
        if path == case.internal and not follow_symlinks:
            return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "stat", fake_stat)
    assert open_result(case).status_code == 404
    assert case.opened == []


def test_open_result_rechecks_identity_before_shell_dispatch(result_case, monkeypatch):
    case = result_case
    original = main._result_file_for_open

    def swapped(task_id, task):
        result = original(task_id, task)
        moved = case.directory / "old.md"
        case.internal.rename(moved)
        case.internal.write_text("replacement", encoding="utf-8")
        return result

    monkeypatch.setattr(main, "_result_file_for_open", swapped)
    assert open_result(case).status_code == 404
    assert case.opened == []


def test_open_result_transcript_and_missing_file(result_case):
    case = result_case
    case.task["output"] = "transcript"
    transcript = case.directory / "transcript.md"
    transcript.write_text("# transcript", encoding="utf-8")
    assert open_result(case).status_code == 200
    assert case.opened == [transcript]
    transcript.unlink()
    assert open_result(case).status_code == 404


@pytest.mark.parametrize("output,folder", [("note", "notes"), ("transcript", "transcripts")])
def test_open_result_default_archives_accept_null_destination(result_case, output, folder):
    case = result_case
    archive_dir = case.workspace / folder
    archive_dir.mkdir()
    archive = archive_dir / "synthetic.md"
    archive.write_text("# synthetic", encoding="utf-8")
    case.task.update(output=output, result={"archived_path": str(archive)})
    case.manifest.write_text(json.dumps({"note_destination": None, "output": output}), encoding="utf-8")
    assert open_result(case).status_code == 200
    assert case.opened == [archive]


def test_open_result_unloaded_history_reads_only_safe_manifest(result_case, monkeypatch):
    case = result_case
    case.manifest.write_text(json.dumps({"output": "note", "runtime": {
        "status": "completed", "step": "corrupt", "elapsed_seconds": "corrupt",
        "logs": 123, "result": {},
    }}), encoding="utf-8")
    monkeypatch.setattr(main, "tasks", {})
    monkeypatch.setattr(main, "restore_task_on_demand", lambda *_: pytest.fail("Opening does not need to load Markdown"))
    assert open_result(case).status_code == 200
    assert case.opened == [case.internal]


def test_open_result_unloaded_corrupt_manifest_returns_fixed_error(result_case, monkeypatch):
    case = result_case
    case.manifest.write_text("{corrupt", encoding="utf-8")
    monkeypatch.setattr(main, "tasks", {})
    response = open_result(case)
    assert response.status_code == 404
    assert str(case.directory) not in response.text
    assert case.opened == []
