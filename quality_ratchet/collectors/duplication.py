from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ..config import Config
from ..errors import CollectorError
from .base import require_tool, run, tool_version

INSTALL = "npm install -g jscpd"


def _ignore_globs(config: Config) -> list[str]:
    globs: list[str] = []
    for e in config.exclude:
        globs.append(f"**/{e}/**" if not any(ch in e for ch in "*?[") else f"**/{e}")
    globs.extend(config.tests_dirs)
    return globs


def collect(config: Config) -> dict[str, float]:
    require_tool("jscpd", INSTALL)
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            "jscpd", "--silent", "--reporters", "json", "--output", tmp,
            "--min-tokens", str(config.duplication_min_tokens),
            "--ignore", ",".join(_ignore_globs(config)),
            *config.include,
        ]
        proc = run(cmd, cwd=config.root, check=False)
        report_path = Path(tmp) / "jscpd-report.json"
        if not report_path.exists():
            raise CollectorError(f"jscpd produced no report ({proc.returncode}): {proc.stderr.strip()[:500]}")
        report = json.loads(report_path.read_text())
    pct = float(report["statistics"]["total"]["percentage"])
    return {"duplication_pct": round(pct, 2)}


def versions(config: Config) -> dict[str, str]:
    return {"jscpd": tool_version(["jscpd", "--version"])}
