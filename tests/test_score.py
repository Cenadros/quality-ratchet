from quality_ratchet.config import DEFAULT_WEIGHTS
from quality_ratchet.score import component, compute_score

INITIAL = {
    "ccn_over_15": 40, "max_ccn": 30, "long_functions": 20,
    "duplication_pct": 4.0, "lint_warnings": 100, "tests_per_kloc": 10.0,
}


def test_component_lower_anchors_at_half():
    assert component(40, 40, "lower") == 0.5
    assert component(0, 40, "lower") == 1.0
    assert component(80, 40, "lower") == 0.0
    assert component(200, 40, "lower") == 0.0  # clamped


def test_component_higher_anchors_at_half():
    assert component(10, 10, "higher") == 0.5
    assert component(20, 10, "higher") == 1.0
    assert component(0, 10, "higher") == 0.0


def test_component_initial_zero():
    assert component(0, 0, "lower") == 1.0
    assert component(3, 0, "lower") == 0.0
    assert component(5, 0, "higher") == 1.0
    assert component(0, 0, "higher") == 0.5


def test_score_is_50_at_initial():
    assert compute_score(dict(INITIAL), INITIAL, DEFAULT_WEIGHTS) == 50


def test_score_moves_with_metrics():
    better = {**INITIAL, "lint_warnings": 0}       # lint component 1.0, weight 0.25 -> +12.5
    worse = {**INITIAL, "duplication_pct": 8.0}    # dup component 0.0, weight 0.25 -> -12.5
    assert compute_score(better, INITIAL, DEFAULT_WEIGHTS) == 62  # round(62.5)
    assert compute_score(worse, INITIAL, DEFAULT_WEIGHTS) == 38   # round(37.5)
