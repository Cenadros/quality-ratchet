from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

CONFIG_FILENAME = "quality-ratchet.yml"
BASELINE_FILENAME = "quality-baseline.json"

DEFAULT_EXCLUDE = ["build", "node_modules", ".build", "Pods", "fastlane", "docs", "*.generated.*", ".git", ".venv"]
DEFAULT_TEST_DIRS = [
    "**/test/**", "**/tests/**", "**/androidTest/**", "**/*Tests/**", "**/*UITests/**", "**/__tests__/**",
]
DEFAULT_TEST_PATTERNS = {
    "kt": r"@Test\b",
    "java": r"@Test\b",
    "swift": r"\bfunc test",
    "ts": r"\b(it|test)\(",
    "tsx": r"\b(it|test)\(",
    "js": r"\b(it|test)\(",
    "py": r"^\s*def test_",
    "rb": r"^\s*(it|test) ",
    "go": r"^func Test",
}
DEFAULT_WEIGHTS = {"complexity": 0.30, "duplication": 0.25, "lint": 0.25, "tests": 0.20}


@dataclass
class Config:
    root: Path
    include: list[str] = field(default_factory=lambda: ["."])
    exclude: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE))
    tests_dirs: list[str] = field(default_factory=lambda: list(DEFAULT_TEST_DIRS))
    tests_patterns: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_TEST_PATTERNS))
    ccn_threshold: int = 15
    function_nloc_threshold: int = 60
    duplication_min_tokens: int = 50
    linters: dict[str, dict] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))

    @property
    def baseline_path(self) -> Path:
        return self.root / BASELINE_FILENAME


def load_config(root: Path) -> Config:
    path = root / CONFIG_FILENAME
    if not path.exists():
        print(f"warning: {CONFIG_FILENAME} not found in {root}, using defaults", file=sys.stderr)
        return Config(root=root)
    raw = yaml.safe_load(path.read_text()) or {}
    tests = raw.get("tests") or {}
    thresholds = raw.get("thresholds") or {}
    return Config(
        root=root,
        include=list(raw.get("include") or ["."]),
        exclude=list(raw.get("exclude") or DEFAULT_EXCLUDE),
        tests_dirs=list(tests.get("dirs") or DEFAULT_TEST_DIRS),
        tests_patterns={**DEFAULT_TEST_PATTERNS, **(tests.get("patterns") or {})},
        ccn_threshold=int(thresholds.get("ccn", 15)),
        function_nloc_threshold=int(thresholds.get("function_nloc", 60)),
        duplication_min_tokens=int((raw.get("duplication") or {}).get("min_tokens", 50)),
        linters=dict(raw.get("linters") or {}),
        weights={**DEFAULT_WEIGHTS, **((raw.get("score") or {}).get("weights") or {})},
    )


def config_hash(config: Config) -> str:
    """Short, stable fingerprint of what Config measures (everything but `root`)."""
    fields = {k: v for k, v in asdict(config).items() if k != "root"}
    digest = hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
    return digest[:12]
