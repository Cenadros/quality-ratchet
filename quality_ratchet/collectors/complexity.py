from __future__ import annotations

import csv
import io

from ..config import Config
from ..files import LIZARD_EXTS, iter_source_files
from .base import require_tool, run, tool_version

INSTALL = "pip install lizard"


def collect(config: Config) -> dict[str, float]:
    require_tool("lizard", INSTALL)
    files = [str(p) for p in iter_source_files(config) if p.suffix.lstrip(".") in LIZARD_EXTS]
    if not files:
        return {"ccn_over_15": 0, "max_ccn": 0, "long_functions": 0}
    proc = run(["lizard", "--csv", *files])
    over = long_functions = max_ccn = 0
    for row in csv.reader(io.StringIO(proc.stdout)):
        if len(row) < 2:
            continue
        try:
            nloc, ccn = int(row[0]), int(row[1])
        except ValueError:
            continue  # header or noise
        if ccn > config.ccn_threshold:
            over += 1
        if nloc > config.function_nloc_threshold:
            long_functions += 1
        max_ccn = max(max_ccn, ccn)
    return {"ccn_over_15": over, "max_ccn": max_ccn, "long_functions": long_functions}


def versions(config: Config) -> dict[str, str]:
    return {"lizard": tool_version(["lizard", "--version"])}
