from __future__ import annotations

import csv
import importlib.metadata
import io
import sys

from ..config import Config
from ..errors import CollectorError
from ..files import LIZARD_EXTS, is_test_path, iter_source_files
from .base import run

INSTALL = "pip install lizard==1.24.0"


def collect(config: Config) -> dict[str, float]:
    try:
        import lizard  # noqa: F401
    except ImportError as e:
        raise CollectorError(f"lizard not importable: {INSTALL}") from e
    files = [
        str(p)
        for p in iter_source_files(config)
        if p.suffix.lstrip(".") in LIZARD_EXTS
        and not is_test_path(p.relative_to(config.root).as_posix(), config.tests_dirs)
    ]
    if not files:
        return {"ccn_over_15": 0, "max_ccn": 0, "long_functions": 0}
    proc = run([sys.executable, "-m", "lizard", "--csv", *files])
    over = long_functions = max_ccn = 0
    rows_parsed = 0
    for row in csv.reader(io.StringIO(proc.stdout)):
        if len(row) < 2:
            continue
        try:
            nloc, ccn = int(row[0]), int(row[1])
        except ValueError:
            continue  # header or noise
        rows_parsed += 1
        if ccn > config.ccn_threshold:
            over += 1
        if nloc > config.function_nloc_threshold:
            long_functions += 1
        max_ccn = max(max_ccn, ccn)
    if rows_parsed == 0 and proc.stdout.strip():
        raise CollectorError("lizard: no parsable rows in --csv output")
    # Metric name is a baseline contract; the threshold behind it is config.ccn_threshold (default 15).
    return {"ccn_over_15": over, "max_ccn": max_ccn, "long_functions": long_functions}


def versions(config: Config) -> dict[str, str]:
    try:
        version = importlib.metadata.version("lizard")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    return {"lizard": version}
