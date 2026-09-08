from __future__ import annotations

from .metrics import GROUPS, METRIC_SPECS


def component(value: float, initial: float, better: str) -> float:
    """0..1 with the initial baseline anchored at 0.5."""
    if initial == 0:
        if better == "lower":
            return 1.0 if value == 0 else 0.0
        return 1.0 if value > 0 else 0.5
    raw = 1 - value / (2 * initial) if better == "lower" else value / (2 * initial)
    return max(0.0, min(1.0, raw))


def compute_score(current: dict[str, float], initial: dict[str, float], weights: dict[str, float]) -> int:
    total = 0.0
    weight_sum = 0.0
    for group, names in GROUPS.items():
        comps = [component(current[n], initial[n], METRIC_SPECS[n][0]) for n in names]
        w = float(weights.get(group, 0.0))
        total += w * (sum(comps) / len(comps))
        weight_sum += w
    return round(100 * total / weight_sum) if weight_sum else 0
