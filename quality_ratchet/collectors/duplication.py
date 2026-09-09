from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ..config import Config
from ..errors import CollectorError
from ..files import iter_source_files, relativize
from .base import require_tool, run, tool_version

INSTALL = "npm install -g jscpd"

_EMPTY_REPORT = {"duplicates": [], "statistics": {"total": {"percentage": 0.0, "duplicatedLines": 0}}}


def _ignore_globs(config: Config) -> list[str]:
    globs: list[str] = []
    for e in config.exclude:
        globs.append(f"**/{e}/**" if not any(ch in e for ch in "*?[") else f"**/{e}")
    globs.extend(config.tests_dirs)
    return globs


def _jscpd_report(config: Config) -> dict:
    """Parsed jscpd JSON report, shared by collect() and explain()."""
    if not iter_source_files(config):
        return _EMPTY_REPORT
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
        report_text = report_path.read_text()
    try:
        return json.loads(report_text)
    except ValueError as e:
        raise CollectorError(f"jscpd: cannot parse report: {e}") from e


def collect(config: Config) -> dict[str, float]:
    report = _jscpd_report(config)
    try:
        pct = float(report["statistics"]["total"]["percentage"])
    except (KeyError, TypeError, ValueError) as e:
        raise CollectorError(f"jscpd: cannot parse report: {e}") from e
    return {"duplication_pct": round(pct, 2)}


def explain(config: Config, top: int) -> list[str]:
    report = _jscpd_report(config)
    duplicates = report.get("duplicates", [])
    stats = report.get("statistics", {}).get("total", {})
    summary = (
        f"clones: {len(duplicates)}  duplicated lines: {int(stats.get('duplicatedLines', 0))}"
        f"  ({stats.get('percentage', 0)}%)"
    )
    lines = [summary]
    per_file: dict[str, int] = {}
    for dup in duplicates:
        dup_lines = int(dup.get("lines", 0))
        for side in ("firstFile", "secondFile"):
            name = dup.get(side, {}).get("name")
            if not name:
                continue
            rel = relativize(config.root, name)
            per_file[rel] = per_file.get(rel, 0) + dup_lines
    lines.extend(
        f"{n:>5} líneas dup  {rel}"
        for rel, n in sorted(per_file.items(), key=lambda kv: kv[1], reverse=True)[:top]
    )
    return lines


def versions(config: Config) -> dict[str, str]:
    return {"jscpd": tool_version(["jscpd", "--version"])}
