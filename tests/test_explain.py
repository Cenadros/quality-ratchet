import subprocess

import pytest

from quality_ratchet.collectors import complexity, duplication, explain_all, lint, tests_ratio
from quality_ratchet.config import Config
from quality_ratchet.errors import ConfigError


def test_complexity_explain_lists_offenders_and_long_functions(fixture_config):
    rows = complexity.explain(fixture_config, 10)
    text = "\n".join(rows)
    assert any("CCN  20" in row and "classify" in row for row in rows)
    idx = next(i for i, row in enumerate(rows) if row.startswith("-- long functions"))
    assert any("longOne" in row for row in rows[idx:])
    assert "longOne" in text


def test_complexity_explain_caps_at_top(fixture_config):
    rows = complexity.explain(fixture_config, 1)
    ccn_rows = [r for r in rows if r.startswith("CCN ")]
    assert len(ccn_rows) == 1


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


def test_explain_all_unknown_group_raises(fixture_config):
    with pytest.raises(ConfigError):
        explain_all(fixture_config, 10, ["not-a-group"])


def test_explain_all_default_groups(fixture_config):
    sections = explain_all(fixture_config, 10, None)
    assert set(sections) == {"complexity", "duplication", "lint", "tests"}
