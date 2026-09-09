from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

from ..config import Config
from ..errors import CollectorError
from ..files import SOURCE_EXTS, is_excluded, is_test_path, iter_source_files
from .base import require_tool, run, tool_version

INSTALL = "brew install scc  (or: go install github.com/boyter/scc/v3@latest)"


def count_test_functions(config: Config) -> int:
    total = 0
    for path in iter_source_files(config):
        rel = path.relative_to(config.root).as_posix()
        if not is_test_path(rel, config.tests_dirs):
            continue
        pattern = config.tests_patterns.get(path.suffix.lstrip("."))
        if not pattern:
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        total += len(re.findall(pattern, text, flags=re.MULTILINE))
    return total


def production_loc(config: Config) -> int:
    require_tool("scc", INSTALL)
    proc = run(["scc", "--by-file", "--format", "json", "--no-cocomo", *config.include], cwd=config.root)
    try:
        languages = json.loads(proc.stdout)
    except ValueError as e:
        raise CollectorError(f"scc: cannot parse JSON output: {e}") from e
    loc = 0
    for lang in languages:
        for f in lang.get("Files", []):
            rel = Path(f["Location"]).as_posix().removeprefix("./")
            if Path(rel).suffix.lstrip(".") not in SOURCE_EXTS:
                continue
            if is_excluded(rel, config.exclude) or is_test_path(rel, config.tests_dirs):
                continue
            loc += int(f.get("Code", 0))
    return loc


def collect(config: Config) -> dict[str, float]:
    tests = count_test_functions(config)
    loc = production_loc(config)
    if loc == 0:
        return {"tests_per_kloc": 0.0}
    return {"tests_per_kloc": round(tests / (loc / 1000), 2)}


def versions(config: Config) -> dict[str, str]:
    return {"scc": tool_version(["scc", "--version"])}


def explain(config: Config, top: int) -> list[str]:
    rows = []
    for entry in config.include:
        sub = replace(config, include=[entry])
        tests = count_test_functions(sub)
        loc = production_loc(sub)
        ratio = round(tests / (loc / 1000), 2) if loc else 0.0
        rows.append((ratio, tests, loc, entry))
    rows.sort(key=lambda r: r[0])
    return [
        f"{ratio:>7.2f} tests/kLOC  tests {tests:>5}  LOC {loc:>7}  {entry}"
        for ratio, tests, loc, entry in rows[:top]
    ]
