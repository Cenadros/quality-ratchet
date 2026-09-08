import json
from pathlib import Path

import pytest

from quality_ratchet.baseline import (
    Baseline, Metric, compare, load_baseline, new_baseline, ratchet, save_baseline,
)
from quality_ratchet.config import DEFAULT_WEIGHTS
from quality_ratchet.errors import ConfigError

CURRENT = {
    "ccn_over_15": 40, "max_ccn": 30, "long_functions": 20,
    "duplication_pct": 4.0, "lint_warnings": 100, "tests_per_kloc": 10.0,
}
VERSIONS = {"lizard": "1.17.10"}


def make() -> Baseline:
    return new_baseline(CURRENT, VERSIONS, "abc1234", DEFAULT_WEIGHTS)


def test_new_baseline_shape():
    b = make()
    assert b.version == 1 and b.commit == "abc1234" and b.score == 50
    assert b.initial == CURRENT
    assert b.metrics["duplication_pct"] == Metric(4.0, "lower", 0.1)
    assert b.metrics["tests_per_kloc"] == Metric(10.0, "higher", 0.2)
    assert b.history == []


def test_roundtrip_json(tmp_path: Path):
    p = tmp_path / "quality-baseline.json"
    save_baseline(p, make())
    data = json.loads(p.read_text())
    assert data["metrics"]["max_ccn"] == {"value": 30, "better": "lower", "tolerance": 0.0}
    assert load_baseline(p) == make()
    assert load_baseline(tmp_path / "missing.json") is None


def test_compare_statuses():
    b = make()
    now = {**CURRENT, "max_ccn": 31, "lint_warnings": 90, "duplication_pct": 4.05, "tests_per_kloc": 9.5}
    by_name = {d.name: d for d in compare(b, now)}
    assert by_name["max_ccn"].status == "fail" and by_name["max_ccn"].delta == 1
    assert by_name["lint_warnings"].status == "improved" and by_name["lint_warnings"].delta == -10
    assert by_name["duplication_pct"].status == "ok"          # within tolerance 0.1
    assert by_name["tests_per_kloc"].status == "fail"         # -0.5 beyond tolerance 0.2
    assert by_name["ccn_over_15"].status == "ok" and by_name["ccn_over_15"].delta == 0


def test_compare_new_metric_and_missing_collector():
    b = make()
    deltas = compare(b, {**CURRENT, "extra": 1})
    assert [d for d in deltas if d.name == "extra"][0].status == "new"
    with pytest.raises(ConfigError, match="max_ccn"):
        compare(b, {k: v for k, v in CURRENT.items() if k != "max_ccn"})


def test_ratchet_only_improves_without_force():
    b = make()
    now = {**CURRENT, "max_ccn": 31, "lint_warnings": 90}
    new, changed = ratchet(b, now, VERSIONS, "def5678", DEFAULT_WEIGHTS)
    assert changed == ["lint_warnings"]
    assert new.metrics["lint_warnings"].value == 90
    assert new.metrics["max_ccn"].value == 30           # regression ignored
    assert new.initial == CURRENT                       # never re-anchored without force
    assert new.commit == "def5678" and new.score > 50
    assert b.metrics["lint_warnings"].value == 100      # input untouched


def test_ratchet_no_change_keeps_commit():
    b = make()
    new, changed = ratchet(b, dict(CURRENT), VERSIONS, "def5678", DEFAULT_WEIGHTS)
    assert changed == [] and new == b


def test_ratchet_force_reanchors_and_records_history():
    b = make()
    now = {**CURRENT, "max_ccn": 31}
    new, changed = ratchet(b, now, {"lizard": "1.18.0"}, "999aaaa", DEFAULT_WEIGHTS, force=True, reason="bump lizard")
    assert changed == ["max_ccn"]
    assert new.metrics["max_ccn"].value == 31
    assert new.initial == now and new.score == 50
    assert new.tool_versions == {"lizard": "1.18.0"}
    assert new.history[-1]["reason"] == "bump lizard"
    assert new.history[-1]["from"]["max_ccn"] == 30 and new.history[-1]["to"]["max_ccn"] == 31


def test_ratchet_force_requires_reason():
    with pytest.raises(ConfigError, match="--reason"):
        ratchet(make(), dict(CURRENT), VERSIONS, "x", DEFAULT_WEIGHTS, force=True)
