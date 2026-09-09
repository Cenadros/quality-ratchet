import os
from pathlib import Path

from quality_ratchet.config import Config
from quality_ratchet.files import is_excluded, is_test_path, iter_source_files, relativize


def test_is_excluded_by_dir_name_and_glob():
    ex = ["build", "*.generated.*"]
    assert is_excluded("android/app/build/x.kt", ex)
    assert is_excluded("ios/Model.generated.swift", ex)
    assert not is_excluded("ios/Model.swift", ex)
    assert not is_excluded("ios/builder/Model.swift", ex)


def test_is_test_path_globs():
    dirs = ["**/src/test/**", "**/*Tests/**"]
    assert is_test_path("android/app/src/test/FooTest.kt", dirs)
    assert is_test_path("ios/Turnify/TurnifyTests/FooTests.swift", dirs)
    assert not is_test_path("ios/Turnify/Turnify/Foo.swift", dirs)
    assert is_test_path("tests/test_x.py", ["**/tests/**"])
    assert is_test_path("test/x.go", ["**/test/**"])


def test_iter_source_files_respects_include_exclude_and_exts(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.kt").write_text("fun a() {}\n")
    (tmp_path / "src" / "notes.md").write_text("# no\n")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "gen.kt").write_text("fun g() {}\n")
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "b.swift").write_text("func b() {}\n")
    cfg = Config(root=tmp_path, include=["src", "build"], exclude=["build"])
    assert iter_source_files(cfg) == [tmp_path / "src" / "a.kt"]


def test_relativize_with_relative_root(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = Config(root=Path("."))
    abs_path = str(tmp_path / "Sources" / "A.swift")
    assert relativize(cfg.root, abs_path) == "Sources/A.swift"


def test_relativize_symlinked_root_both_directions(tmp_path: Path):
    real_root = Path(os.path.realpath(tmp_path))
    # tmp_path may itself go through a symlink (e.g. /tmp -> /private/tmp on macOS);
    # both the given root and the tool-reported absolute path can land on either side.
    abs_via_tmp_path = str(tmp_path / "Sources" / "A.swift")
    assert relativize(real_root, abs_via_tmp_path) == "Sources/A.swift"
    abs_via_real_root = str(real_root / "Sources" / "B.swift")
    assert relativize(tmp_path, abs_via_real_root) == "Sources/B.swift"


def test_relativize_outside_root_stays_unchanged():
    outside = "/some/other/place/File.kt"
    assert relativize(Path("/tmp/project"), outside) == outside


def test_relativize_already_relative_passes_through():
    assert relativize(Path("/tmp/project"), "Sources/A.swift") == "Sources/A.swift"
