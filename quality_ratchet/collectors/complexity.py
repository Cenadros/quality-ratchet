from __future__ import annotations

import csv
import importlib.metadata
import io
import sys

from ..config import Config
from ..errors import CollectorError
from ..files import LIZARD_EXTS, is_test_path, iter_source_files, relativize
from .base import run

INSTALL = "pip install lizard==1.24.0"

# lizard --csv columns: NLOC,CCN,token,PARAM,length,location,file,function,long_name,start,end
_COL_NLOC, _COL_CCN, _COL_FILE, _COL_FUNCTION = 0, 1, 6, 7


def _lizard_rows(config: Config) -> list[dict]:
    """Parsed lizard --csv rows for production files, shared by collect() and explain()."""
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
        return []
    proc = run([sys.executable, "-m", "lizard", "--csv", *files])
    rows: list[dict] = []
    for row in csv.reader(io.StringIO(proc.stdout)):
        if len(row) <= _COL_FUNCTION:
            continue
        try:
            nloc, ccn = int(row[_COL_NLOC]), int(row[_COL_CCN])
        except ValueError:
            continue  # header or noise
        rows.append({"nloc": nloc, "ccn": ccn, "file": row[_COL_FILE], "function": row[_COL_FUNCTION]})
    if not rows and proc.stdout.strip():
        raise CollectorError("lizard: no parsable rows in --csv output")
    return rows


def collect(config: Config) -> dict[str, float]:
    rows = _lizard_rows(config)
    over = sum(1 for r in rows if r["ccn"] > config.ccn_threshold)
    long_functions = sum(1 for r in rows if r["nloc"] > config.function_nloc_threshold)
    max_ccn = max((r["ccn"] for r in rows), default=0)
    # Metric name is a baseline contract; the threshold behind it is config.ccn_threshold (default 15).
    return {"ccn_over_15": over, "max_ccn": max_ccn, "long_functions": long_functions}


def explain(config: Config, top: int) -> list[str]:
    rows = _lizard_rows(config)
    complex_rows = sorted(
        (r for r in rows if r["ccn"] > config.ccn_threshold), key=lambda r: r["ccn"], reverse=True
    )[:top]
    lines = [
        f"CCN {r['ccn']:>3}  NLOC {r['nloc']:>4}  {relativize(config.root, r['file'])}  {r['function']}"
        for r in complex_rows
    ]
    shown = {(r["file"], r["function"], r["nloc"], r["ccn"]) for r in complex_rows}
    long_rows = sorted(
        (
            r
            for r in rows
            if r["nloc"] > config.function_nloc_threshold
            and (r["file"], r["function"], r["nloc"], r["ccn"]) not in shown
        ),
        key=lambda r: r["nloc"],
        reverse=True,
    )[:top]
    lines.append(f"-- long functions (NLOC > {config.function_nloc_threshold})")
    lines.extend(
        f"NLOC {r['nloc']:>4}  CCN {r['ccn']:>3}  {relativize(config.root, r['file'])}  {r['function']}"
        for r in long_rows
    )
    return lines


def versions(config: Config) -> dict[str, str]:
    try:
        version = importlib.metadata.version("lizard")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    return {"lizard": version}
