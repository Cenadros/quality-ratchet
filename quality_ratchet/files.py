from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from .config import Config

# Languages lizard can parse (function-level CCN/NLOC).
LIZARD_EXTS = frozenset(
    [
        "c", "cc", "cpp", "cxx", "h", "hpp", "hh", "java", "kt", "kts", "swift", "js", "jsx", "ts", "tsx",
        "py", "rb", "go", "rs", "php", "scala", "m", "mm", "cs", "lua",
    ]
)
# Everything we count as "production or test code" for LOC purposes.
SOURCE_EXTS = LIZARD_EXTS | frozenset(["sh", "bash", "zsh"])


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
    for pat in tests_dirs:
        if fnmatch.fnmatch(rel, pat.replace("**", "*")):
            return True
        # "**/tests/**" requires a segment before "tests/" once collapsed to "*/tests/*",
        # so a repo-root "tests/..." would never match it. Also try the pattern with its
        # leading "**/" stripped so a root-level test dir matches too.
        if pat.startswith("**/") and fnmatch.fnmatch(rel, pat[3:].replace("**", "*")):
            return True
    return False


def relativize(root: Path, path: str) -> str:
    """Return `path` relative to `root` when it is inside root; otherwise unchanged.

    Tools like swiftlint report absolute paths regardless of `root` being relative
    (e.g. the default `--root .`), so both sides are resolved before comparing.
    """
    p = Path(path)
    if not p.is_absolute():
        return p.as_posix()
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return p.as_posix()


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
