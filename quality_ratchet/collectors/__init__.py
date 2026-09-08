from __future__ import annotations

from ..config import Config
from ..errors import CollectorError
from ..metrics import METRIC_SPECS
from . import complexity, duplication, lint, tests_ratio

COLLECTORS = [complexity, duplication, lint, tests_ratio]


def collect_all(config: Config) -> tuple[dict[str, float], dict[str, str]]:
    metrics: dict[str, float] = {}
    versions: dict[str, str] = {}
    for collector in COLLECTORS:
        metrics.update(collector.collect(config))
        versions.update(collector.versions(config))
    missing = [m for m in METRIC_SPECS if m not in metrics]
    if missing:
        raise CollectorError(f"collectors produced no value for: {', '.join(missing)}")
    return metrics, versions
