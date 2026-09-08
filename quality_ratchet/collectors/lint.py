from __future__ import annotations

import json
from collections.abc import Callable

from ..config import Config
from ..errors import CollectorError
from .base import require_tool, run, tool_version


def _count_swiftlint(out: str) -> int:
    return len(json.loads(out or "[]"))


def _count_eslint(out: str) -> int:
    return sum(len(f.get("messages", [])) for f in json.loads(out or "[]"))


def _count_ruff(out: str) -> int:
    return len(json.loads(out or "[]"))


LINTERS: dict[str, dict] = {
    "swiftlint": {
        "cmd": ["swiftlint", "lint", "--quiet", "--reporter", "json"],
        "count": _count_swiftlint, "install": "brew install swiftlint", "version": ["swiftlint", "version"],
    },
    "eslint": {
        "cmd": ["npx", "eslint", ".", "-f", "json"],
        "count": _count_eslint, "install": "npm install -g eslint", "version": ["npx", "eslint", "--version"],
    },
    "ruff": {
        "cmd": ["ruff", "check", ".", "--output-format", "json"],
        "count": _count_ruff, "install": "pip install ruff", "version": ["ruff", "--version"],
    },
}


def collect(config: Config) -> dict[str, float]:
    total = 0
    for name, opts in config.linters.items():
        spec = LINTERS.get(name)
        if spec is None:
            raise CollectorError(f"unknown linter '{name}' (known: {', '.join(sorted(LINTERS))})")
        require_tool(spec["cmd"][0], spec["install"])
        opts = opts or {}
        cwd = config.root / opts.get("cwd", ".")
        cmd = list(spec["cmd"]) + [str(a) for a in opts.get("args", [])]
        proc = run(cmd, cwd=cwd, check=False)  # linters exit non-zero when they find issues
        if not proc.stdout.strip():
            raise CollectorError(f"{name} produced no output ({proc.returncode}): {proc.stderr.strip()[:500]}")
        try:
            count: Callable[[str], int] = spec["count"]
            total += count(proc.stdout)
        except (ValueError, KeyError, TypeError) as e:
            raise CollectorError(f"{name}: cannot parse output: {e}") from e
    return {"lint_warnings": total}


def versions(config: Config) -> dict[str, str]:
    return {name: tool_version(LINTERS[name]["version"]) for name in config.linters if name in LINTERS}
