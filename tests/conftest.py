from pathlib import Path

import pytest

from quality_ratchet.config import Config


def write_fixture_repo(root: Path) -> None:
    (root / "Sources" / "FooTests").mkdir(parents=True)
    (root / "src" / "main").mkdir(parents=True)
    (root / "src" / "test").mkdir(parents=True)

    branches = "\n".join(f'    if n == {i} {{ out = "v{i}" }}' for i in range(1, 20))
    (root / "Sources" / "Complex.swift").write_text(
        "func classify(_ n: Int) -> String {\n    var out = \"\"\n" + branches + "\n    return out\n}\n"
    )
    body = "\n".join(f"    x += {i} * {i}" for i in range(1, 71))
    (root / "src" / "main" / "Long.kt").write_text("fun longOne(): Int {\n    var x = 0\n" + body + "\n    return x\n}\n")
    dup = (
        "export function summarize(values: number[]): string {\n"
        "    const total = values.reduce((acc, value) => acc + value, 0);\n"
        "    const average = values.length === 0 ? 0 : total / values.length;\n"
        "    const maximum = Math.max(...values);\n"
        "    const minimum = Math.min(...values);\n"
        "    const spread = maximum - minimum;\n"
        "    const label = spread > average ? 'wide' : 'narrow';\n"
        "    const parts = [`total=${total}`, `avg=${average.toFixed(2)}`, `max=${maximum}`];\n"
        "    parts.push(`min=${minimum}`, `spread=${spread}`, `label=${label}`);\n"
        "    return parts.join(', ');\n"
        "}\n"
    )
    (root / "src" / "main" / "dup_a.ts").write_text(dup)
    (root / "src" / "main" / "dup_b.ts").write_text(dup)
    (root / "Sources" / "FooTests" / "FooTests.swift").write_text(
        "import XCTest\nfinal class FooTests: XCTestCase {\n    func testA() {}\n    func testB() {}\n}\n"
    )
    (root / "src" / "test" / "BarTest.kt").write_text(
        "import org.junit.Test\nclass BarTest {\n    @Test fun bar() {}\n}\n"
    )


@pytest.fixture(scope="session")
def fixture_repo(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("fixture_repo")
    write_fixture_repo(root)
    return root


@pytest.fixture
def fixture_config(fixture_repo: Path) -> Config:
    return Config(root=fixture_repo, include=["Sources", "src"], tests_dirs=["**/*Tests/**", "**/src/test/**"])
