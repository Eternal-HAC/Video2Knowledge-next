"""Schema-1 reference projection only; not connected to the product or logs."""
from __future__ import annotations

import math
import re

from product_info import PRODUCT_NAME, VERSION

PACKAGES = ("fastapi", "uvicorn", "yt-dlp", "faster-whisper", "sherpa-onnx",
            "openai", "av", "Pillow", "mcp", "PyInstaller", "pytest", "PyYAML")
VERSION_RE = re.compile(r"[0-9]{1,4}(?:\.[0-9]{1,4}){1,3}(?:(?:a|b|rc)[0-9]{1,4}|\.post[0-9]{1,4}|-(?:beta|rc)\.[0-9]{1,4})?")
ENUMS = {
    "mode": {"portable", "source"},
    "stage": {"queued", "downloading", "transcribing", "summarizing", "exporting", "completed", "failed", "cancelled"},
    # These are proposed stable codes, not a classification of current raw errors.
    "error_code": {"none", "llm_unavailable", "transcript_unavailable", "output_unavailable", "cancelled", "internal_error"},
    "model_kind": {"remote", "local", "none"},
}


def safe_version(value) -> str | None:
    return value if isinstance(value, str) and VERSION_RE.fullmatch(value) else None


def _number(value, maximum, integer=False):
    if type(value) not in ((int,) if integer else (int, float)):
        return None
    return value if 0 <= value <= maximum and math.isfinite(value) else None


def build_snapshot(runtime, environment) -> dict:
    runtime = runtime if type(runtime) is dict else {}
    environment = environment if type(environment) is dict else {}
    packages = environment.get("packages")
    packages = packages if type(packages) is dict else {}
    fields = {}
    for key, allowed in ENUMS.items():
        value = runtime.get(key)
        fields[key] = value if isinstance(value, str) and value in allowed else "unknown"
    fields["duration_seconds"] = _number(runtime.get("duration_seconds"), 604800)
    fields["segment_count"] = _number(runtime.get("segment_count"), 1000000, integer=True)
    os_name = environment.get("os")
    return {
        "schema_version": 1, "product": PRODUCT_NAME, "version": VERSION,
        "runtime": fields,
        "environment": {
            "os": os_name if isinstance(os_name, str) and os_name in {"Windows", "Linux", "Darwin"} else "unknown",
            "os_major": _number(environment.get("os_major"), 999, integer=True),
            "python": safe_version(environment.get("python")),
            "packages": {name: safe_version(packages.get(name)) for name in PACKAGES},
        },
    }
