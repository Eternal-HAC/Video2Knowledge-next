"""Local evidence utilities. No download, build, execution or publishing."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import re
import sys
from pathlib import Path

from product_info import PRODUCT_NAME, VERSION
from scripts.diagnostic_contract import PACKAGES, build_snapshot, safe_version
from scripts.quality_io import SafeArgumentParser, checked_path, read_text, write_report

ASSET_NAME = f"{PRODUCT_NAME}-{VERSION}-portable.exe"


def environment_snapshot() -> dict:
    versions = {}
    for name in PACKAGES:
        try:
            versions[name] = safe_version(importlib.metadata.version(name))
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    release = re.match(r"[0-9]{1,3}(?:\.|$)", platform.release())
    environment = {"os": platform.system(), "os_major": int(release[0].rstrip(".")) if release else None,
                   "python": ".".join(str(i) for i in sys.version_info[:3]), "packages": versions}
    result = build_snapshot({}, environment)["environment"]
    return {"schema_version": 1, "product": PRODUCT_NAME, "version": VERSION, **result}


def _hash(path: Path) -> tuple[str, int]:
    target = checked_path(path)
    digest, size = hashlib.sha256(), 0
    with target.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def verify_assets(candidate: Path, downloaded: Path, checksums: Path, metadata: Path) -> dict:
    try:
        lines = read_text(checksums, 8192).strip().splitlines()
        match = re.fullmatch(r"([a-fA-F0-9]{64}) [ *]" + re.escape(ASSET_NAME), lines[0]) if len(lines) == 1 else None
        if not match:
            return {"passed": False, "error_code": "checksum_invalid"}
        try:
            info = json.loads(read_text(metadata, 16384))
        except (ValueError, TypeError):
            return {"passed": False, "error_code": "metadata_invalid"}
        if (type(info) is not dict or info.get("name") != ASSET_NAME
                or type(info.get("size")) is not int or info["size"] <= 0
                or not isinstance(info.get("digest"), str)
                or not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", info["digest"])):
            return {"passed": False, "error_code": "metadata_invalid"}
        left_hash, left_size = _hash(candidate)
        right_hash, right_size = _hash(downloaded)
        if not (left_hash == right_hash == match[1].lower() == info["digest"][7:].lower()
                and left_size == right_size == info["size"]):
            return {"passed": False, "error_code": "asset_mismatch"}
        return {"passed": True, "asset": ASSET_NAME, "sha256": left_hash, "size": left_size}
    except (OSError, ValueError):
        return {"passed": False, "error_code": "input_unavailable"}


def main(argv=None) -> int:
    parser = SafeArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    env = sub.add_parser("environment")
    env.add_argument("--output", type=Path)
    verify = sub.add_parser("verify-assets")
    for name in ("candidate", "downloaded", "checksums", "metadata"):
        verify.add_argument("--" + name, type=Path, required=True)
    verify.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = environment_snapshot() if args.command == "environment" else verify_assets(args.candidate, args.downloaded, args.checksums, args.metadata)
    try:
        write_report(result, args.output)
    except ValueError:
        write_report({"passed": False, "error_code": "output_unavailable"})
        return 2
    return 0 if result.get("passed", True) else 1


if __name__ == "__main__":
    sys.exit(main())
