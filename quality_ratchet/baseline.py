from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from .errors import ConfigError
from .metrics import METRIC_SPECS
from .score import compute_score

EPS = 1e-9


@dataclass
class Metric:
    value: float
    better: str
    tolerance: float = 0.0


@dataclass
class Baseline:
    version: int
    commit: str
    tool_versions: dict[str, str]
    initial: dict[str, float]
    metrics: dict[str, Metric]
    score: int
    history: list[dict] = field(default_factory=list)
    config_hash: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["metrics"] = {k: asdict(m) for k, m in self.metrics.items()}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Baseline:
        return cls(
            version=int(d["version"]),
            commit=str(d.get("commit", "unknown")),
            tool_versions=dict(d.get("tool_versions", {})),
            initial={k: float(v) for k, v in d["initial"].items()},
            metrics={k: Metric(**m) for k, m in d["metrics"].items()},
            score=int(d["score"]),
            history=list(d.get("history", [])),
            config_hash=str(d.get("config_hash", "")),
        )


@dataclass
class Delta:
    name: str
    baseline: float | None
    now: float
    delta: float
    status: str  # ok | improved | fail | new


def load_baseline(path: Path) -> Baseline | None:
    if not path.exists():
        return None
    try:
        return Baseline.from_dict(json.loads(path.read_text()))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        raise ConfigError(f"cannot read {path}: {e}") from e


def save_baseline(path: Path, baseline: Baseline) -> None:
    path.write_text(json.dumps(baseline.to_dict(), indent=2, ensure_ascii=False) + "\n")


def new_baseline(current: dict[str, float], tool_versions: dict[str, str], commit: str,
                 weights: dict[str, float], config_hash: str) -> Baseline:
    initial = dict(current)
    metrics = {name: Metric(value, *METRIC_SPECS[name]) for name, value in current.items() if name in METRIC_SPECS}
    return Baseline(
        version=1, commit=commit, tool_versions=dict(tool_versions), initial=initial, metrics=metrics,
        score=compute_score(current, initial, weights), config_hash=config_hash,
    )


def compare(baseline: Baseline, current: dict[str, float]) -> list[Delta]:
    missing = [name for name in baseline.metrics if name not in current]
    if missing:
        raise ConfigError(f"metric(s) in baseline have no collector: {', '.join(missing)}")
    deltas: list[Delta] = []
    for name, now in current.items():
        m = baseline.metrics.get(name)
        if m is None:
            deltas.append(Delta(name, None, now, 0.0, "new"))
            continue
        delta = round(now - m.value, 4)
        worse = delta if m.better == "lower" else -delta
        if worse > m.tolerance + EPS:
            status = "fail"
        elif worse < -EPS:
            status = "improved"
        else:
            status = "ok"
        deltas.append(Delta(name, m.value, now, delta, status))
    return deltas


def ratchet(baseline: Baseline, current: dict[str, float], tool_versions: dict[str, str], commit: str,
            weights: dict[str, float], config_hash: str, force: bool = False,
            reason: str | None = None) -> tuple[Baseline, list[str]]:
    if force and not reason:
        raise ConfigError("--force requires --reason")
    if baseline.config_hash and baseline.config_hash != config_hash and not force:
        raise ConfigError(
            f"config changed since baseline (hash {baseline.config_hash} → {config_hash}): "
            "re-anchor with update --force --reason '<why>'"
        )
    new = copy.deepcopy(baseline)
    changed: list[str] = []
    for d in compare(baseline, current):
        if d.status == "new":
            if d.name in METRIC_SPECS:
                new.metrics[d.name] = Metric(d.now, *METRIC_SPECS[d.name])
                new.initial[d.name] = d.now
                changed.append(d.name)
        elif d.status == "improved" or (force and d.delta != 0):
            new.metrics[d.name].value = d.now
            changed.append(d.name)
    if force:
        new.history.append({
            "date": date.today().isoformat(), "reason": reason,  # noqa: DTZ011 (local date is intentional)
            "from": {k: m.value for k, m in baseline.metrics.items()},
            "to": {k: v for k, v in current.items() if k in METRIC_SPECS},
        })
        new.initial = {k: v for k, v in current.items() if k in METRIC_SPECS}
    if changed or force:
        new.commit = commit
        new.tool_versions = dict(tool_versions)
        new.score = compute_score({n: m.value for n, m in new.metrics.items()}, new.initial, weights)
    if force or not baseline.config_hash:
        new.config_hash = config_hash
    return new, changed
