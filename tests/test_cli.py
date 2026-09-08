import json
import shutil
from pathlib import Path

import pytest

from quality_ratchet.cli import main
from tests.conftest import write_fixture_repo


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    write_fixture_repo(tmp_path)
    (tmp_path / "quality-ratchet.yml").write_text(
        "include: [Sources, src]\ntests:\n  dirs: ['**/*Tests/**', '**/src/test/**']\n"
    )
    return tmp_path


def add_complex_function(repo: Path) -> None:
    branches = "\n".join(f'    if n == {i} {{ out = "w{i}" }}' for i in range(1, 25))
    (repo / "Sources" / "More.swift").write_text(
        "func classify2(_ n: Int) -> String {\n    var out = \"\"\n" + branches + "\n    return out\n}\n"
    )


def simplify_function(repo: Path) -> None:
    # Same file, same line count (28), CCN 1: only complexity improves; LOC, duplication and tests ratio stay put.
    lines = "\n".join(f"    out += n * {i}" for i in range(1, 25))
    (repo / "Sources" / "More.swift").write_text(
        "func classify2(_ n: Int) -> Int {\n    var out = 0\n" + lines + "\n    return out\n}\n"
    )


def test_check_creates_baseline_first_time(repo, capsys):
    assert main(["--root", str(repo), "check"]) == 0
    out = capsys.readouterr().out
    assert "baseline inicial" in out
    data = json.loads((repo / "quality-baseline.json").read_text())
    # Not 50: this fixture's quality-ratchet.yml configures no linter, so lint_warnings
    # starts at 0. score.component() anchors a lower-is-better metric already at 0 to
    # full credit (1.0), not the neutral 0.5 (see test_score.py::test_component_initial_zero)
    # -> round(100 * (0.5*.30 + 0.5*.25 + 1.0*.25 + 0.5*.20)) == 62.
    assert data["score"] == 62
    assert data["metrics"]["ccn_over_15"]["value"] == 1


def test_check_fails_on_regression_and_report_never_fails(repo, capsys):
    main(["--root", str(repo), "check"])
    add_complex_function(repo)
    assert main(["--root", str(repo), "check"]) == 1
    out = capsys.readouterr().out
    assert "ccn_over_15" in out and "FAIL" in out
    assert main(["--root", str(repo), "report"]) == 0


def test_check_passes_on_improvement(repo):
    add_complex_function(repo)
    main(["--root", str(repo), "check"])          # baseline with 2 complex functions
    simplify_function(repo)                       # deleting the file would shift LOC and raise duplication_pct
    assert main(["--root", str(repo), "check"]) == 0


def test_update_ratchets_only_improvements(repo, capsys):
    add_complex_function(repo)
    main(["--root", str(repo), "check"])
    simplify_function(repo)
    assert main(["--root", str(repo), "update"]) == 0
    data = json.loads((repo / "quality-baseline.json").read_text())
    assert data["metrics"]["ccn_over_15"]["value"] == 1
    assert data["score"] > 50
    add_complex_function(repo)
    assert main(["--root", str(repo), "update"]) == 0
    data = json.loads((repo / "quality-baseline.json").read_text())
    assert data["metrics"]["ccn_over_15"]["value"] == 1   # regression not written
    assert "ignorado" in capsys.readouterr().out


def test_update_force_requires_reason(repo, capsys):
    main(["--root", str(repo), "check"])
    add_complex_function(repo)
    assert main(["--root", str(repo), "update", "--force"]) == 2
    assert "--reason" in capsys.readouterr().err
    assert main(["--root", str(repo), "update", "--force", "--reason", "accept"]) == 0
    data = json.loads((repo / "quality-baseline.json").read_text())
    assert data["metrics"]["ccn_over_15"]["value"] == 2
    assert data["history"][-1]["reason"] == "accept"


def test_missing_tool_exits_2(repo, monkeypatch, capsys):
    monkeypatch.setenv("PATH", "/nonexistent")
    assert main(["--root", str(repo), "check"]) == 2
    assert "not found" in capsys.readouterr().err


def test_github_annotations(repo, capsys, tmp_path, monkeypatch):
    main(["--root", str(repo), "check"])
    add_complex_function(repo)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert main(["--root", str(repo), "check", "--github"]) == 1
    assert "::error title=quality-ratchet::ccn_over_15" in capsys.readouterr().out
    assert "| ccn_over_15 |" in summary.read_text()


def test_init_writes_config_and_baseline(tmp_path):
    write_fixture_repo(tmp_path)
    (tmp_path / "Sources" / ".swiftlint.yml").write_text("disabled_rules: []\n")
    rc = main(["--root", str(tmp_path), "init"])
    cfg = (tmp_path / "quality-ratchet.yml").read_text()
    assert "swiftlint" in cfg and "cwd: Sources" in cfg
    if shutil.which("swiftlint") is None:
        assert rc == 2 and not (tmp_path / "quality-baseline.json").exists()  # tool missing fails loudly
    else:
        assert rc == 0 and (tmp_path / "quality-baseline.json").exists()
