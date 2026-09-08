from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from .config import Config

# Languages lizard can parse (function-level CCN/NLOC).
LIZARD_EXTS = frozenset(
    "c cc cpp cxx h hpp hh java kt kts swift js jsx ts tsx py rb go rs php scala m mm cs lua".split()
)
# Everything we count as "production or test code" for LOC purposes.
SOURCE_EXTS = LIZARD_EXTS | frozenset("sh bash zsh".split())


def is_excluded(rel: str, exclude: list[str]) -> bool:
    parts = rel.split("/")
    for pat in exclude:
        if any(ch in pat for ch in "*?["):
            if any(fnmatch.fnmatch(part, pat) for part in parts):
                return True
        elif pat in parts:
            return True
    return False


def is_test_path(rel: str, tests_dirs: list[str]) -> bool:
    # fnmatch's "*" already crosses "/" so "**" collapses to "*".
    return any(fnmatch.fnmatch(rel, pat.replace("**", "*")) for pat in tests_dirs)


def iter_source_files(config: Config) -> list[Path]:
    found: set[Path] = set()
    root = config.root
    for inc in config.include:
        base = root / inc
        if base.is_file():
            if base.suffix.lstrip(".") in SOURCE_EXTS:
                found.add(base)
            continue
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            rel_dir = Path(dirpath).relative_to(root).as_posix()
            prefix = "" if rel_dir == "." else rel_dir + "/"
            dirnames[:] = sorted(d for d in dirnames if not is_excluded(prefix + d, config.exclude))
            for name in filenames:
                rel = prefix + name
                if Path(name).suffix.lstrip(".") not in SOURCE_EXTS:
                    continue
                if is_excluded(rel, config.exclude):
                    continue
                found.add(root / rel)
    return sorted(found)
