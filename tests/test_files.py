from pathlib import Path

from quality_ratchet.config import Config
from quality_ratchet.files import is_excluded, is_test_path, iter_source_files


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
