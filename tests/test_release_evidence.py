import hashlib
import importlib
import json

import pytest


@pytest.fixture
def tool():
    return importlib.import_module("scripts.release_evidence")


@pytest.fixture
def asset_files(tool, tmp_path):
    raw = b"synthetic executable bytes; never execute"
    digest = hashlib.sha256(raw).hexdigest()
    candidate, downloaded = tmp_path / "candidate.exe", tmp_path / "downloaded.exe"
    candidate.write_bytes(raw)
    downloaded.write_bytes(raw)
    checksums, metadata = tmp_path / "SHA256SUMS.txt", tmp_path / "metadata.json"
    checksums.write_text(f"{digest}  {tool.ASSET_NAME}\n", encoding="utf-8")
    metadata.write_text(json.dumps({"name": tool.ASSET_NAME, "size": len(raw), "digest": "sha256:" + digest}), encoding="utf-8")
    return candidate, downloaded, checksums, metadata


def test_four_way_comparison(tool, asset_files):
    result = tool.verify_assets(*asset_files)
    assert result["passed"] and result["size"] > 0
    assert result["asset"] == tool.ASSET_NAME


@pytest.mark.parametrize("mutation", ["candidate", "downloaded", "digest", "name", "size", "duplicate", "traversal", "bad_json"])
def test_asset_corruption_fails_with_fixed_error(tool, asset_files, mutation):
    candidate, downloaded, sums, metadata = asset_files
    if mutation in {"candidate", "downloaded"}:
        (candidate if mutation == "candidate" else downloaded).write_bytes(b"mismatch")
    elif mutation == "duplicate":
        sums.write_text(sums.read_text() * 2)
    elif mutation == "traversal":
        sums.write_text(sums.read_text().replace(tool.ASSET_NAME, "../secret.exe"))
    elif mutation == "bad_json":
        metadata.write_text("PRIVATE_INVALID_JSON")
    else:
        obj = json.loads(metadata.read_text())
        obj[mutation] = {"digest": "sha256:" + "0" * 64, "name": "PRIVATE_PATH", "size": True}[mutation]
        metadata.write_text(json.dumps(obj))
    result = tool.verify_assets(*asset_files)
    assert not result["passed"]
    assert result["error_code"] in {"asset_mismatch", "checksum_invalid", "metadata_invalid"}
    assert "PRIVATE" not in json.dumps(result)


def test_environment_has_no_paths_and_no_subprocess(tool, monkeypatch):
    import socket
    import subprocess
    def forbidden(*args, **kwargs):
        raise AssertionError("offline only")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    result = tool.environment_snapshot()
    assert result["python"] and result["product"] == "Video2Knowledge"
    assert set(result["packages"]) == set(tool.PACKAGES)
    assert "path" not in json.dumps(result).lower()


def test_output_is_exclusive_and_report_failure_does_not_echo(tmp_path):
    io = importlib.import_module("scripts.quality_io")
    target = tmp_path / "report.json"
    io.write_report({"passed": True}, target)
    with pytest.raises(ValueError, match="output_unavailable"):
        io.write_report({"passed": False}, target)
    assert json.loads(target.read_text())["passed"]


def test_link_and_hardlink_paths_rejected_when_supported(tmp_path):
    io = importlib.import_module("scripts.quality_io")
    real = tmp_path / "real.json"
    real.write_text("{}")
    hard = tmp_path / "hard.json"
    hard.hardlink_to(real)
    with pytest.raises(ValueError, match="input_unavailable"):
        io.read_text(hard)
    # Symbolic-link privileges are unavailable on this host; the lexical guard
    # also explicitly checks Windows reparse attributes (unit-tested below).


def test_reparse_component_guard(monkeypatch, tmp_path):
    io = importlib.import_module("scripts.quality_io")
    original = io.is_link
    monkeypatch.setattr(io, "is_link", lambda path: path == tmp_path or original(path))
    with pytest.raises(ValueError, match="output_unavailable"):
        io.write_report({}, tmp_path / "new.json")
    assert not (tmp_path / "new.json").exists()


@pytest.mark.parametrize("module,args", [
    ("scripts.evaluate_notes", ["--PRIVATE_PATH_SENTINEL"]),
    ("scripts.release_evidence", ["environment", "--PRIVATE_PATH_SENTINEL"]),
    ("scripts.release_evidence", ["PRIVATE_PATH_SENTINEL"]),
])
def test_cli_bad_arguments_never_echo_values(module, args, capsys):
    with pytest.raises(SystemExit) as exc:
        importlib.import_module(module).main(args)
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "PRIVATE_PATH_SENTINEL" not in captured.err + captured.out
    assert "arguments_invalid" in captured.err


def test_cli_output_failure_is_fixed_and_nonzero(tmp_path, capsys):
    tool = importlib.import_module("scripts.evaluate_notes")
    target = tmp_path / "PRIVATE_PATH_SENTINEL.json"
    target.write_text("preserve")
    assert tool.main(["--output", str(target)]) == 2
    out = capsys.readouterr().out
    assert "output_unavailable" in out and "PRIVATE_PATH_SENTINEL" not in out
    assert target.read_text() == "preserve"


@pytest.mark.parametrize("content", [b"\xff", b"x" * 20])
def test_bounded_text_read_rejects_bad_encoding_and_size(tmp_path, content):
    io = importlib.import_module("scripts.quality_io")
    path = tmp_path / "input.json"
    path.write_bytes(content)
    with pytest.raises(ValueError, match="input_unavailable"):
        io.read_text(path, limit=10)


def test_cli_verify_assets_returns_success_without_execution(tool, asset_files, capsys, monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("never execute assets"))
    args = ["verify-assets"]
    for key, path in zip(("candidate", "downloaded", "checksums", "metadata"), asset_files):
        args.extend(["--" + key, str(path)])
    assert tool.main(args) == 0
    assert json.loads(capsys.readouterr().out)["passed"]
