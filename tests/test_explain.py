import subprocess
from pathlib import Path

import pytest

from quality_ratchet.cli import main
from quality_ratchet.collectors import complexity, duplication, explain_all, lint, tests_ratio
from quality_ratchet.config import Config
from quality_ratchet.errors import CollectorError, ConfigError
from tests.conftest import write_fixture_repo


@pytest.fixture
def repo_for_explain(tmp_path: Path) -> Path:
    write_fixture_repo(tmp_path)
    (tmp_path / "quality-ratchet.yml").write_text(
        "include: [Sources, src]\ntests:\n  dirs: ['**/*Tests/**', '**/src/test/**']\n"
    )
    return tmp_path


def test_complexity_explain_lists_offenders_and_long_functions(fixture_config):
    rows = complexity.explain(fixture_config, 10)
    text = "\n".join(rows)
    assert any("CCN  20" in row and "classify" in row for row in rows)
    idx = next(i for i, row in enumerate(rows) if row.startswith("-- funciones largas"))
    assert any("longOne" in row for row in rows[idx:])
    assert "longOne" in text


def test_complexity_explain_caps_at_top(fixture_config):
    rows = complexity.explain(fixture_config, 1)
    ccn_rows = [r for r in rows if r.startswith("CCN ")]
    assert len(ccn_rows) == 1


def test_complexity_explain_falls_back_to_top_ccn_when_none_over_threshold(tmp_path):
    from quality_ratchet.config import Config as Cfg

    # A single function with CCN 10 (< default threshold 15) and NLOC well under 60.
    branches = "\n".join(f'    if n == {i} {{ out = "v{i}" }}' for i in range(1, 10))
    (tmp_path / "Small.swift").write_text(
        'func classifySmall(_ n: Int) -> String {\n    var out = ""\n' + branches + "\n    return out\n}\n"
    )
    cfg = Cfg(root=tmp_path)
    rows = complexity.explain(cfg, 10)
    assert rows[0] == f"-- top CCN (ninguna supera el umbral {cfg.ccn_threshold})"
    assert any("classifySmall" in row for row in rows[1:])
    assert not any(row.startswith("-- funciones largas") for row in rows)


def test_explain_all_wraps_collector_error_per_section(fixture_config, monkeypatch):
    def boom(config, top):
        raise CollectorError("jscpd not found: x")

    monkeypatch.setattr(duplication, "explain", boom)
    sections = explain_all(fixture_config, 10, None)
    assert sections["duplication"] == ["(no disponible: jscpd not found: x)"]
    assert sections["complexity"]  # unaffected


def test_cli_explain_survives_one_section_failing(repo_for_explain, capsys, monkeypatch):
    def boom(config, top):
        raise CollectorError("jscpd not found: x")

    monkeypatch.setattr(duplication, "explain", boom)
    assert main(["--root", str(repo_for_explain), "explain"]) == 0
    out = capsys.readouterr().out
    assert "## complexity" in out
    assert "(no disponible: jscpd not found: x)" in out


def test_duplication_explain_summary_and_files(fixture_config):
    rows = duplication.explain(fixture_config, 10)
    assert rows[0].startswith("clones: ")
    text = "\n".join(rows)
    assert "src/main/dup_a.ts" in text
    assert "src/main/dup_b.ts" in text


def test_duplication_explain_empty_repo(tmp_path):
    rows = duplication.explain(Config(root=tmp_path), 10)
    assert rows[0].startswith("clones: 0")


def test_lint_explain_por_regla_y_por_fichero(fixture_repo, monkeypatch):
    fake = subprocess.CompletedProcess(
        args=["swiftlint"],
        returncode=0,
        stdout=(
            f'[{{"file": "{fixture_repo}/Sources/A.swift", "rule_id": "file_length"}},'
            f'{{"file": "{fixture_repo}/Sources/A.swift", "rule_id": "line_length"}},'
            f'{{"file": "{fixture_repo}/Sources/B.swift", "rule_id": "file_length"}}]'
        ),
        stderr="",
    )
    monkeypatch.setattr(lint, "require_tool", lambda name, hint: name)
    monkeypatch.setattr(lint, "run", lambda cmd, cwd=None, check=True: fake)
    cfg = Config(root=fixture_repo, linters={"swiftlint": {"cwd": "Sources"}})
    rows = lint.explain(cfg, 10)
    assert "   2  file_length" in rows
    assert "   1  line_length" in rows
    assert "   2  Sources/A.swift" in rows


def test_lint_explain_no_linters_is_empty(fixture_repo):
    assert lint.explain(Config(root=fixture_repo), 10) == []


def test_tests_ratio_explain_two_rows(fixture_config):
    rows = tests_ratio.explain(fixture_config, 10)
    assert len(rows) == 2
    joined = "\n".join(rows)
    assert "Sources" in joined and "src" in joined
    assert all("tests/kLOC" in row for row in rows)


def test_tests_ratio_explain_groups_by_first_path_segment(tmp_path):
    (tmp_path / "a" / "x").mkdir(parents=True)
    (tmp_path / "a" / "y").mkdir(parents=True)
    (tmp_path / "a" / "x" / "One.kt").write_text("fun one(): Int {\n    return 1\n}\n")
    (tmp_path / "a" / "y" / "Two.kt").write_text("fun two(): Int {\n    return 2\n}\n")
    cfg = Config(root=tmp_path, include=["a/x", "a/y"])
    rows = tests_ratio.explain(cfg, 10)
    assert len(rows) == 1
    assert rows[0].endswith("  a")


def test_explain_all_unknown_group_raises(fixture_config):
    with pytest.raises(ConfigError):
        explain_all(fixture_config, 10, ["not-a-group"])


def test_explain_all_default_groups(fixture_config):
    sections = explain_all(fixture_config, 10, None)
    assert set(sections) == {"complexity", "duplication", "lint", "tests"}
