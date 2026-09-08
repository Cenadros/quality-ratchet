import pytest

from quality_ratchet.collectors import complexity, duplication
from quality_ratchet.collectors.base import require_tool
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
