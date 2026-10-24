"""G2 manifest behavior locks. Synthetic fixtures, no network or user workspace."""
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import stat

import pytest

from backend import task_repository as repository


@pytest.mark.parametrize("legacy", [
    {"task_id": "v142", "source_url": "https://example.org/video"},
    {"task_id": "beta1", "runtime": {"status": "failed"}, "subtitle_import": True},
    {"task_id": "beta2", "note_template_snapshot": {"id": "custom", "layout": "{{content}}"}},
    {"task_id": "beta3", "origin": "agent", "favorite": True, "future": {"version": 9}},
])
def test_legacy_fields_survive_merge(tmp_path, legacy):
    path = tmp_path / "task.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")
    repository.merge(path, {"title": "更新标题"})
    assert repository.read(path) == {**legacy, "title": "更新标题"}


def test_concurrent_updates_are_serial_and_leave_no_temporary_files(tmp_path):
    path = tmp_path / "task.json"
    repository.merge(path, {"favorite": True, "future": {"kept": True}})

    def increment(_):
        def change(payload):
            payload["count"] = payload.get("count", 0) + 1
        repository.update(path, change)

    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(increment, range(150)))
        list(pool.map(lambda i: repository.merge(path, {f"field-{i}": i}), range(60)))
    payload = repository.read(path)
    assert payload["count"] == 150
    assert payload["favorite"] is True
    assert payload["future"] == {"kept": True}
    assert all(payload[f"field-{i}"] == i for i in range(60))
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("content", ["{broken", "[]", '"string"', "null"])
def test_corrupt_read_is_compatible_but_write_preserves_evidence(tmp_path, content):
    path = tmp_path / "task.json"
    path.write_text(content, encoding="utf-8")
    assert repository.read(path) == {}
    with pytest.raises(OSError):
        repository.merge(path, {"favorite": True})
    assert path.read_text(encoding="utf-8") == content


def test_failed_replace_preserves_original_and_cleans_temporary(tmp_path, monkeypatch):
    path = tmp_path / "task.json"
    repository.merge(path, {"favorite": True})
    def fail(*args):
        raise OSError("synthetic replace failure")
    monkeypatch.setattr(repository.os, "replace", fail)
    with pytest.raises(OSError):
        repository.merge(path, {"favorite": False})
    assert repository.read(path) == {"favorite": True}
    assert list(tmp_path.iterdir()) == [path]


def test_callback_failure_does_not_write(tmp_path):
    path = tmp_path / "task.json"
    repository.merge(path, {"favorite": True})
    def fail(payload):
        payload["favorite"] = False
        raise ValueError("synthetic callback failure")
    with pytest.raises(ValueError):
        repository.update(path, fail)
    assert repository.read(path)["favorite"] is True


@pytest.mark.parametrize("mode,attributes,links", [
    (stat.S_IFLNK, 0, 1), (stat.S_IFDIR, 0, 1),
    (stat.S_IFREG, 0x400, 1), (stat.S_IFREG, 0, 2),
])
def test_non_regular_manifests_are_rejected_without_os_link_privilege(tmp_path, monkeypatch, mode, attributes, links):
    path = tmp_path / "task.json"
    info = SimpleNamespace(st_mode=mode, st_file_attributes=attributes, st_nlink=links)
    monkeypatch.setattr(type(path), "lstat", lambda self: info)
    assert repository.read(path) == {}
    with pytest.raises(OSError, match="独立普通文件"):
        repository.merge(path, {"favorite": True})
