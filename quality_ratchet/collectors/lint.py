from __future__ import annotations

import json
from collections.abc import Callable

from ..config import Config
from ..errors import CollectorError
from ..files import relativize
from .base import require_tool, run, tool_version


def _count_swiftlint(out: str) -> int:
    return len(json.loads(out or "[]"))


def _count_eslint(out: str) -> int:
    return sum(len(f.get("messages", [])) for f in json.loads(out or "[]"))


def _count_ruff(out: str) -> int:
    return len(json.loads(out or "[]"))


def _items_swiftlint(out: str) -> list[tuple[str, str]]:
    return [(item.get("file", "?"), item.get("rule_id", "?")) for item in json.loads(out or "[]")]


def _items_eslint(out: str) -> list[tuple[str, str]]:
    return [
        (f.get("filePath", "?"), m.get("ruleId") or "?")
        for f in json.loads(out or "[]")
        for m in f.get("messages", [])
    ]


def _items_ruff(out: str) -> list[tuple[str, str]]:
    return [(item.get("filename", "?"), item.get("code", "?")) for item in json.loads(out or "[]")]


LINTERS: dict[str, dict] = {
    "swiftlint": {
        "cmd": ["swiftlint", "lint", "--quiet", "--reporter", "json"],
        "count": _count_swiftlint, "items": _items_swiftlint,
        "install": "brew install swiftlint", "version": ["swiftlint", "version"],
    },
    "eslint": {
        "cmd": ["npx", "eslint", ".", "-f", "json"],
        "count": _count_eslint, "items": _items_eslint,
        "install": "npm install -g eslint", "version": ["npx", "eslint", "--version"],
    },
    "ruff": {
        "cmd": ["ruff", "check", ".", "--output-format", "json"],
        "count": _count_ruff, "items": _items_ruff,
        "install": "pip install ruff", "version": ["ruff", "--version"],
    },
}


def _run_linter(name: str, opts: dict, config: Config) -> str:
    """Invoke one configured linter and return its raw stdout, shared by collect() and explain()."""
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
    return proc.stdout


def collect(config: Config) -> dict[str, float]:
    total = 0
    for name, opts in config.linters.items():
        out = _run_linter(name, opts, config)
        try:
            count: Callable[[str], int] = LINTERS[name]["count"]
            total += count(out)
        except (ValueError, KeyError, TypeError) as e:
            raise CollectorError(f"{name}: cannot parse output: {e}") from e
    return {"lint_warnings": total}


def explain(config: Config, top: int) -> list[str]:
    lines: list[str] = []
    for name, opts in config.linters.items():
        out = _run_linter(name, opts, config)
        try:
            items: list[tuple[str, str]] = LINTERS[name]["items"](out)
        except (ValueError, KeyError, TypeError) as e:
            raise CollectorError(f"{name}: cannot parse output: {e}") from e
        by_rule: dict[str, int] = {}
        by_file: dict[str, int] = {}
        for file, rule in items:
            by_rule[rule] = by_rule.get(rule, 0) + 1
            rel = relativize(config.root, file)
            by_file[rel] = by_file.get(rel, 0) + 1
        lines.append(f"-- {name}: por regla")
        lines.extend(
            f"{n:>4}  {rule}" for rule, n in sorted(by_rule.items(), key=lambda kv: kv[1], reverse=True)[:top]
        )
        lines.append(f"-- {name}: por fichero")
        lines.extend(
            f"{n:>4}  {file}" for file, n in sorted(by_file.items(), key=lambda kv: kv[1], reverse=True)[:top]
        )
    return lines


def versions(config: Config) -> dict[str, str]:
    return {name: tool_version(LINTERS[name]["version"]) for name in config.linters if name in LINTERS}
