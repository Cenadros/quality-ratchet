import subprocess

import pytest

from quality_ratchet.collectors import complexity, duplication, lint, tests_ratio
from quality_ratchet.collectors.base import require_tool
from quality_ratchet.config import Config
from quality_ratchet.errors import CollectorError


def test_require_tool_missing_has_install_hint():
    with pytest.raises(CollectorError, match="definitely-not-a-tool-xyz not found: pip install nothing"):
        require_tool("definitely-not-a-tool-xyz", "pip install nothing")


def test_require_tool_present():
    assert require_tool("python3", "n/a").endswith("python3")


def test_complexity_on_fixture(fixture_config):
    out = complexity.collect(fixture_config)
    assert out["ccn_over_15"] == 1
    assert out["max_ccn"] == 20
    assert out["long_functions"] == 1


def test_complexity_empty_repo(tmp_path):
    from quality_ratchet.config import Config
    assert complexity.collect(Config(root=tmp_path)) == {"ccn_over_15": 0, "max_ccn": 0, "long_functions": 0}


def test_complexity_versions(fixture_config):
    assert complexity.versions(fixture_config)["lizard"] != "unknown"


def test_duplication_on_fixture(fixture_config):
    out = duplication.collect(fixture_config)
    assert 0 < out["duplication_pct"] < 50


def test_duplication_ignores_test_dirs(fixture_config, fixture_repo):
    # Copy the duplicated file into a test dir: percentage must not rise (tests are ignored).
    before = duplication.collect(fixture_config)["duplication_pct"]
    (fixture_repo / "src" / "test" / "dup_c.ts").write_text((fixture_repo / "src" / "main" / "dup_a.ts").read_text())
    try:
        after = duplication.collect(fixture_config)["duplication_pct"]
    finally:
        (fixture_repo / "src" / "test" / "dup_c.ts").unlink()
    assert after <= before


def test_lint_counts_swiftlint_json(fixture_repo, monkeypatch):
    fake = subprocess.CompletedProcess(args=["swiftlint"], returncode=0, stdout='[{"rule_id":"a"},{"rule_id":"b"}]', stderr="")
    monkeypatch.setattr(lint, "require_tool", lambda name, hint: name)
    monkeypatch.setattr(lint, "run", lambda cmd, cwd=None, check=True: fake)
    cfg = Config(root=fixture_repo, linters={"swiftlint": {"cwd": "Sources"}})
    assert lint.collect(cfg) == {"lint_warnings": 2}


def test_lint_no_linters_is_zero(fixture_repo):
    assert lint.collect(Config(root=fixture_repo)) == {"lint_warnings": 0}


def test_lint_unknown_linter(fixture_repo):
    with pytest.raises(CollectorError, match="unknown linter 'pylint'"):
        lint.collect(Config(root=fixture_repo, linters={"pylint": {}}))


def test_lint_missing_tool_fails_loudly(fixture_repo):
    lint.LINTERS["fake-linter"] = {"cmd": ["fake-linter-bin"], "count": lambda out: 0,
                                   "install": "install fake", "version": ["fake-linter-bin", "--version"]}
    try:
        with pytest.raises(CollectorError, match="fake-linter-bin not found: install fake"):
            lint.collect(Config(root=fixture_repo, linters={"fake-linter": {}}))
    finally:
        del lint.LINTERS["fake-linter"]


def test_count_test_functions(fixture_config):
    assert tests_ratio.count_test_functions(fixture_config) == 3


def test_production_loc_excludes_tests(fixture_config):
    loc = tests_ratio.production_loc(fixture_config)
    assert 90 <= loc <= 130  # Complex.swift (~23) + Long.kt (~74) + 2 x dup (~11 each) = ~119


def test_tests_per_kloc(fixture_config):
    out = tests_ratio.collect(fixture_config)
    assert 20 < out["tests_per_kloc"] < 40  # 3 tests / ~0.119 kloc ≈ 25
