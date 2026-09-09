from pathlib import Path

from quality_ratchet.config import DEFAULT_EXCLUDE, DEFAULT_WEIGHTS, Config, config_hash, load_config


def test_defaults_when_config_missing(tmp_path: Path, capsys):
    cfg = load_config(tmp_path)
    assert cfg.include == ["."]
    assert cfg.exclude == DEFAULT_EXCLUDE
    assert cfg.ccn_threshold == 15
    assert cfg.function_nloc_threshold == 60
    assert cfg.duplication_min_tokens == 50
    assert cfg.linters == {}
    assert cfg.weights == DEFAULT_WEIGHTS
    assert cfg.baseline_path == tmp_path / "quality-baseline.json"
    assert "quality-ratchet.yml not found" in capsys.readouterr().err


def test_reads_yaml_and_merges_patterns(tmp_path: Path):
    (tmp_path / "quality-ratchet.yml").write_text(
        "include: [ios, android]\n"
        "exclude: [build]\n"
        "tests:\n  dirs: ['**/Tests/**']\n  patterns: {swift: 'func test'}\n"
        "thresholds: {ccn: 10, function_nloc: 40}\n"
        "duplication: {min_tokens: 70}\n"
        "linters:\n  swiftlint: {cwd: ios/Turnify}\n"
        "score:\n  weights: {lint: 0.5}\n"
    )
    cfg = load_config(tmp_path)
    assert cfg.include == ["ios", "android"]
    assert cfg.exclude == ["build"]
    assert cfg.tests_dirs == ["**/Tests/**"]
    assert cfg.tests_patterns["swift"] == "func test"
    assert cfg.tests_patterns["kt"] == r"@Test\b"  # default kept
    assert cfg.ccn_threshold == 10 and cfg.function_nloc_threshold == 40
    assert cfg.duplication_min_tokens == 70
    assert cfg.linters == {"swiftlint": {"cwd": "ios/Turnify"}}
    assert cfg.weights["lint"] == 0.5 and cfg.weights["tests"] == 0.20


def test_config_hash_ignores_root_but_reacts_to_content(tmp_path: Path):
    cfg_a = Config(root=tmp_path)
    cfg_b = Config(root=tmp_path / "elsewhere")
    assert config_hash(cfg_a) == config_hash(cfg_b)

    cfg_c = Config(root=tmp_path, exclude=["other"])
    assert config_hash(cfg_a) != config_hash(cfg_c)
