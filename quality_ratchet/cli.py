from __future__ import annotations

import argparse
import os
import subprocess
import sys
import traceback
from pathlib import Path

import yaml

from . import github
from .baseline import Baseline, Delta, compare, load_baseline, new_baseline, ratchet, save_baseline
from .collectors import collect_all
from .config import CONFIG_FILENAME, DEFAULT_EXCLUDE, Config, config_hash, load_config
from .errors import CollectorError, ConfigError
from .files import is_excluded
from .score import compute_score

STATUS_LABEL = {"ok": "ok", "improved": "ok  ↑", "fail": "FAIL", "new": "new"}


def git_commit(root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True, check=False
        )
        return proc.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def print_table(deltas: list[Delta], baseline_score: int, score: int, failed: bool) -> None:
    width = max(len("metric"), *(len(d.name) for d in deltas))
    print(f"{'metric':<{width}}  {'baseline':>9} {'now':>8} {'delta':>7}   status")
    for d in deltas:
        base = "—" if d.baseline is None else f"{d.baseline:g}"
        print(f"{d.name:<{width}}  {base:>9} {d.now:>8g} {d.delta:>+7g}   {STATUS_LABEL[d.status]}")
    diff = score - baseline_score
    label = "FAIL" if failed else ("ok  ↑" if diff > 0 else "ok")
    print(f"{'score':<{width}}  {baseline_score:>9} {score:>8} {diff:>+7d}   {label}")


def warn_versions(baseline: Baseline, versions: dict[str, str]) -> None:
    for tool, ver in versions.items():
        old = baseline.tool_versions.get(tool)
        if old and old != ver:
            print(f"warning: {tool} version changed ({old} → {ver}); numbers may shift without code changes. "
                  f"Re-anchor with: quality-ratchet update --force --reason 'bump {tool}'", file=sys.stderr)


def warn_config_change(baseline: Baseline, config: Config) -> None:
    current_hash = config_hash(config)
    if baseline.config_hash and baseline.config_hash != current_hash:
        print("warning: quality-ratchet.yml changed since the baseline; update will require --force --reason",
              file=sys.stderr)


def _measure(root: Path) -> tuple[Config, dict[str, float], dict[str, str]]:
    config = load_config(root)
    current, versions = collect_all(config)
    return config, current, versions


def _create_baseline(config: Config, current: dict[str, float], versions: dict[str, str]) -> Baseline:
    baseline = new_baseline(current, versions, git_commit(config.root), config.weights, config_hash(config))
    save_baseline(config.baseline_path, baseline)
    print(f"baseline inicial creada en {config.baseline_path.name} (score {baseline.score}), nada que comparar")
    return baseline


def cmd_check(args: argparse.Namespace, gate: bool = True) -> int:
    config, current, versions = _measure(Path(args.root))
    baseline = load_baseline(config.baseline_path)
    if baseline is None:
        if gate:
            _create_baseline(config, current, versions)
            return 0
        # report never creates or writes a baseline: pretend everything is "new" against
        # an empty baseline, anchored at the neutral score (50).
        deltas = [Delta(name, None, now, 0.0, "new") for name, now in current.items()]
        score = compute_score(current, current, config.weights)
        print_table(deltas, score, score, failed=False)
        print("sin baseline: quality-ratchet check la crea")
        return 0
    deltas = compare(baseline, current)
    score = compute_score(current, baseline.initial, config.weights)
    failed = any(d.status == "fail" for d in deltas)
    print_table(deltas, baseline.score, score, failed)
    warn_versions(baseline, versions)
    warn_config_change(baseline, config)
    if getattr(args, "github", False):
        github.emit(deltas, baseline.score, score)
    return 1 if (gate and failed) else 0


def cmd_report(args: argparse.Namespace) -> int:
    return cmd_check(args, gate=False)


def cmd_update(args: argparse.Namespace) -> int:
    config, current, versions = _measure(Path(args.root))
    baseline = load_baseline(config.baseline_path)
    if baseline is None:
        _create_baseline(config, current, versions)
        return 0
    new, changed = ratchet(baseline, current, versions, git_commit(config.root), config.weights,
                           config_hash(config), force=args.force, reason=args.reason)
    ignored = [d.name for d in compare(baseline, current) if d.status == "fail" and d.name not in changed]
    for name in ignored:
        print(f"warning: {name} empeoró; ignorado (usa --force --reason para aceptarlo)")
    if changed or args.force:
        save_baseline(config.baseline_path, new)
        print(f"baseline actualizada: {', '.join(changed) or 'sin métricas mejoradas'} (score {baseline.score} → {new.score})")
    else:
        print("baseline sin cambios")
    return 0


def _find_swiftlint_config(root: Path) -> Path | None:
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        prefix = "" if rel_dir == "." else rel_dir + "/"
        dirnames[:] = sorted(d for d in dirnames if not is_excluded(prefix + d, DEFAULT_EXCLUDE))
        if ".swiftlint.yml" in sorted(filenames):
            return Path(dirpath) / ".swiftlint.yml"
    return None


def detect_linters(root: Path) -> dict[str, dict]:
    found: dict[str, dict] = {}
    cfg = _find_swiftlint_config(root)
    if cfg is not None:
        found["swiftlint"] = {"cwd": cfg.parent.relative_to(root).as_posix()}
    if (root / "ruff.toml").exists() or (root / ".ruff.toml").exists():  # noqa: SIM114 (kept separate for clarity)
        found["ruff"] = {}
    elif (root / "pyproject.toml").exists() and "[tool.ruff]" in (root / "pyproject.toml").read_text():
        found["ruff"] = {}
    if any((root / n).exists() for n in ("eslint.config.js", "eslint.config.mjs", ".eslintrc.json", ".eslintrc.js", ".eslintrc.cjs")):
        found["eslint"] = {}
    return found


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root)
    cfg_path = root / CONFIG_FILENAME
    if cfg_path.exists():
        print(f"{CONFIG_FILENAME} ya existe; no se sobrescribe", file=sys.stderr)
    else:
        doc = {
            "version": 1,
            "include": ["."],
            "exclude": list(Config(root=root).exclude),
            "tests": {"dirs": list(Config(root=root).tests_dirs)},
            "thresholds": {"ccn": 15, "function_nloc": 60},
            "duplication": {"min_tokens": 50},
            "linters": detect_linters(root),
            "score": {"weights": dict(Config(root=root).weights)},
        }
        cfg_path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
        print(f"{CONFIG_FILENAME} creado (linters detectados: {', '.join(doc['linters']) or 'ninguno'})")
    config, current, versions = _measure(root)
    if load_baseline(config.baseline_path) is None:
        _create_baseline(config, current, versions)
    else:
        print(f"{config.baseline_path.name} ya existe; no se sobrescribe", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quality-ratchet", description="Monotonic code-quality gate")
    parser.add_argument("--root", default=".", help="project root (default: cwd)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check", help="compare against baseline; exit 1 on regression")
    p.add_argument("--github", action="store_true", help="emit GitHub annotations and step summary")
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("update", help="write improvements into the baseline")
    p.add_argument("--force", action="store_true", help="also accept regressions (requires --reason)")
    p.add_argument("--reason", help="why the baseline is being loosened")
    p.set_defaults(func=cmd_update)
    sub.add_parser("report", help="print metrics and score; always exit 0").set_defaults(func=cmd_report)
    sub.add_parser("init", help="create quality-ratchet.yml and the initial baseline").set_defaults(func=cmd_init)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (CollectorError, ConfigError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except Exception:  # noqa: BLE001 (deliberate: an internal crash must never read as exit 1/a quality regression)
        print(f"internal error: {traceback.format_exc()}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
