"""Bounded explicit input and create-only reports for local offline tools.

This rejects existing links/reparse components; it is not a sandbox against a
concurrent privileged process replacing directories between checks and open.
"""
from __future__ import annotations

import json
import argparse
import os
import stat
from pathlib import Path


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default message echoes unknown arguments, including paths.
        self.exit(2, '{"passed": false, "error_code": "arguments_invalid"}\n')


def is_link(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def checked_path(path: Path, *, output: bool = False) -> Path:
    code = "output_unavailable" if output else "input_unavailable"
    try:
        # Inspect lexical components before any resolution could conceal a link.
        raw = Path(path)
        if ".." in raw.parts:
            raise ValueError(code)
        target = Path(os.path.abspath(raw))
        for component in reversed((target, *target.parents)):
            if component.exists() or component.is_symlink():
                if is_link(component):
                    raise ValueError(code)
        if output:
            if target.exists() or not target.parent.is_dir():
                raise ValueError(code)
        else:
            info = target.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError(code)
        return target
    except (OSError, ValueError, TypeError):
        raise ValueError(code) from None


def read_text(path: Path, limit: int = 512 * 1024) -> str:
    try:
        target = checked_path(path)
        with target.open("rb") as stream:
            payload = stream.read(limit + 1)
        if len(payload) > limit:
            raise ValueError("input_unavailable")
        return payload.decode("utf-8-sig")
    except (OSError, ValueError, UnicodeError):
        raise ValueError("input_unavailable") from None


def write_report(report: dict, path: Path | None = None) -> None:
    payload = json.dumps(report, ensure_ascii=True, indent=2, allow_nan=False) + "\n"
    if path is None:
        print(payload, end="")
        return
    try:
        target = checked_path(path, output=True)
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
    except (OSError, ValueError):
        raise ValueError("output_unavailable") from None
