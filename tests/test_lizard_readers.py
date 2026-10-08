import textwrap

import lizard
import pytest

from quality_ratchet import lizard_readers
from quality_ratchet.collectors import complexity
from quality_ratchet.config import Config


@pytest.fixture(autouse=True, scope="module")
def _readers():
    lizard_readers.install()


def functions(filename: str, code: str) -> dict[str, tuple[int, int]]:
    """name -> (first line, last line) of every function lizard reports."""
    info = lizard.analyze_file.analyze_source_code(filename, textwrap.dedent(code).lstrip("\n"))
    names = [f.name for f in info.function_list]
    assert len(names) == len(set(names)), f"a name is reported twice: {names}"
    return {f.name: (f.start_line, f.end_line) for f in info.function_list}


def ccn(filename: str, code: str, name: str) -> int:
    info = lizard.analyze_file.analyze_source_code(filename, textwrap.dedent(code).lstrip("\n"))
    return next(f.cyclomatic_complexity for f in info.function_list if f.name == name)


# --- Kotlin ---


def test_kotlin_one_line_lambda_does_not_swallow_the_function():
    # The reproduction of the bug: with the stock reader neither function is reported.
    found = functions("a.kt", """
        fun outer(xs: List<Int>) {
            xs.forEach { x -> println(x) }
            println("a")
        }

        fun next() {
            println("b")
        }
    """)
    assert found == {"outer": (1, 4), "next": (6, 8)}


def test_kotlin_lambda_belongs_to_the_function_it_is_written_in():
    code = """
        fun outer(xs: List<Int>): Int {
            return xs.count { x ->
                if (x > 1) {
                    true
                } else {
                    false
                }
            }
        }
    """
    assert functions("a.kt", code) == {"outer": (1, 9)}
    assert ccn("a.kt", code, "outer") == 2


def test_kotlin_lambda_inside_a_when_branch():
    code = """
        fun f(x: Int, xs: List<Int>): Int {
            return when (x) {
                1 -> xs.count { y -> y > 1 }
                2 -> 2
                else -> 0
            }
        }

        fun g() {
            println(1)
        }
    """
    assert functions("a.kt", code) == {"f": (1, 7), "g": (9, 11)}
    assert ccn("a.kt", code, "f") == 3  # three branches, as the stock reader counts them


def test_kotlin_get_and_set_calls_are_not_accessors():
    found = functions("a.kt", """
        fun f(m: MutableMap<String, Int>): Int {
            m.set("k", 1)
            val a = m.get("k")
            return a ?: 0
        }

        fun g() {
            println(1)
        }
    """)
    assert found == {"f": (1, 5), "g": (7, 9)}


def test_kotlin_property_accessors_are_functions():
    found = functions("a.kt", """
        class A {
            val x: Int
                get() = 1
            var y: Int = 0
                private set
            var z: List<Int> = emptyList()
                set(value) {
                    field = value
                }

            fun g() {
                println(1)
            }
        }
    """)
    assert found == {"get": (3, 3), "set": (7, 9), "g": (11, 13)}


def test_kotlin_accessor_with_a_return_type():
    found = functions("a.kt", """
        class A {
            val z: List<Int>
                get(): List<Int> {
                    return emptyList()
                }
        }
    """)
    assert found == {"get": (3, 5)}


def test_kotlin_expression_body_ends_with_the_expression():
    found = functions("a.kt", """
        fun plan(xs: List<String>): Int {
            fun matches(a: String, b: String) = a.trim().equals(b, ignoreCase = true)
            fun longer(a: String) = a
                .trim()
                .length
            var n = 0
            for (x in xs) {
                if (matches(x, "a")) n += longer(x)
            }
            return n
        }

        fun after() {
            println(1)
        }
    """)
    assert found == {"matches": (2, 2), "longer": (3, 5), "plan": (1, 11), "after": (13, 15)}


def test_kotlin_expression_body_with_a_block():
    code = """
        class A {
            fun pick(x: Int) = when (x) {
                1 -> "a"
                else -> "b"
            }

            fun run(xs: List<Int>) = xs.map { it + 1 }

            fun g() {
                println(1)
            }
        }
    """
    assert functions("a.kt", code) == {"pick": (2, 5), "run": (7, 7), "g": (9, 11)}
    assert ccn("a.kt", code, "pick") == 2


def test_kotlin_extension_function_keeps_its_bounds():
    found = functions("a.kt", """
        fun String.shout(): String {
            return uppercase()
        }

        fun <T> List<T>.second(): T {
            return this[1]
        }

        fun g() {
            println(1)
        }
    """)
    assert found == {"String.shout": (1, 3), "List.second": (5, 7), "g": (9, 11)}


def test_kotlin_declarations_without_a_body_are_not_functions():
    found = functions("a.kt", """
        abstract class A {
            abstract fun a(): Int
            abstract fun b(x: Int): List<Int>

            fun g() {
                println(1)
            }
        }

        fun interface Action {
            fun run()
        }

        interface Dao {
            fun find(id: String): String?

            fun findOrEmpty(id: String): String {
                return find(id) ?: ""
            }
        }
    """)
    assert found == {"g": (5, 7), "findOrEmpty": (17, 19)}


def test_kotlin_type_and_comma_do_not_swallow_a_brace():
    found = functions("a.kt", """
        fun f(xs: List<Item>): List<Item> {
            val kinds = xs.map { it.type }
            return xs.sortedWith(
                compareBy(
                    { it.type },
                    { it.name },
                )
            )
        }

        fun g() {
            println(1)
        }
    """)
    assert found == {"f": (1, 9), "g": (11, 13)}


def test_kotlin_name_in_backticks_with_spaces():
    found = functions("a.kt", """
        class T {
            fun `a name with spaces, a comma and it's quote`() {
                check(true)
            }

            fun g() {
                println(1)
            }
        }
    """)
    assert found == {"`a name with spaces, a comma and it's quote`": (2, 4), "g": (6, 8)}


def test_kotlin_expression_body_closed_by_the_enclosing_brace_on_its_line():
    found = functions("a.kt", """
        class A { fun one() = 1 }

        fun g() {
            println(1)
        }
    """)
    assert found == {"one": (1, 1), "g": (3, 5)}


def test_kotlin_function_type_parameter_with_a_default_lambda():
    found = functions("a.kt", """
        fun stop(onDone: () -> Unit = {}) {
            onDone()
        }

        fun g(block: (Int) -> Int): (Int) -> Int {
            return block
        }
    """)
    assert found == {"stop": (1, 3), "g": (5, 7)}


def test_kotlin_statement_after_a_local_expression_function_stays_outside_it():
    code = """
        fun outer(xs: List<Int>): Int {
            fun double(x: Int) = x * 2
            if (xs.isEmpty()) return 0
            return double(xs.first())
        }
    """
    assert functions("a.kt", code) == {"double": (2, 2), "outer": (1, 5)}
    assert ccn("a.kt", code, "outer") == 2
    assert ccn("a.kt", code, "double") == 1


def test_kotlin_expression_body_at_the_end_of_the_file():
    assert functions("a.kt", "fun a() {}\nfun f() = 1\n") == {"a": (1, 1), "f": (2, 2)}


def test_kotlin_expression_body_ending_in_a_call_to_get():
    found = functions("a.kt", """
        class Prefs {
            var token: String?
                get() = get(KEY)
                set(value) = set(KEY, value)

            fun after() {
                println(1)
            }
        }

        fun top() = get(1)
        fun last() {
            println(2)
        }
    """)
    assert found == {"get": (3, 3), "set": (4, 4), "after": (6, 8), "top": (11, 11), "last": (12, 14)}


def test_kotlin_annotation_in_a_return_type_is_not_a_new_declaration():
    found = functions("a.kt", """
        fun f(): @Composable () -> Unit {
            return {}
        }

        abstract class A {
            abstract fun bodyless(): Int
            @Test
            fun g() {
                println(1)
            }
        }
    """)
    assert found == {"f": (1, 3), "g": (8, 10)}


def test_kotlin_expression_body_ending_in_a_generic_type():
    found = functions("a.kt", """
        class A {
            fun f(x: Any) = x as List<String>
            fun g() {
                println(1)
            }
        }
    """)
    assert found == {"f": (2, 2), "g": (3, 5)}


def test_kotlin_expression_body_with_if_else_over_several_lines():
    code = """
        fun f(x: Int) =
            if (x > 0)
                "a"
            else
                "b"

        fun g(x: Int) = try {
            x
        }
        catch (e: Exception) {
            0
        }
    """
    assert functions("a.kt", code) == {"f": (1, 5), "g": (7, 12)}


def test_kotlin_extension_receiver_with_a_nullable_type_argument():
    found = functions("a.kt", """
        fun Map<String, Int?>.total(): Int {
            return values.sumOf { it ?: 0 }
        }
    """)
    assert found == {"Map.total": (1, 3)}


def test_kotlin_when_subject_with_a_lambda():
    code = """
        fun f(xs: List<Int>): Int {
            return when (xs.firstOrNull { it > 0 }) {
                1 -> 1
                2 -> 2
                else -> 0
            }
        }
    """
    assert functions("a.kt", code) == {"f": (1, 7)}
    assert ccn("a.kt", code, "f") == 3


# --- Swift ---


def test_swift_calls_named_like_accessors_are_not_functions():
    found = functions("a.swift", """
        final class Store {
            private(set) var count = 0

            func save(_ value: Int) {
                UserDefaults.standard.set(value, forKey: "k")
                count = Wrapper.init(value).get()
            }

            func load() -> Int {
                return count
            }
        }
    """)
    assert found == {"save": (4, 7), "load": (9, 11)}


def test_swift_accessors_and_initializers_are_functions():
    found = functions("a.swift", """
        struct S {
            var stored = 0 {
                didSet {
                    print(stored)
                }
            }
            var x: Int {
                get {
                    return stored
                }
                set(newValue) {
                    stored = newValue
                }
            }

            init?(text: String) {
                guard let value = Int(text) else { return nil }
                stored = value
            }
        }
    """)
    assert found == {"didSet": (3, 5), "get": (8, 10), "set": (11, 13), "init?": (16, 19)}


def test_swift_directives_do_not_swallow_the_rest_of_the_line():
    found = functions("a.swift", """
        func widgets() -> Int {
            if #available(iOS 17, *) {
                return 1
            }
            let predicate = #Predicate<Shift> { shift in
                shift.date > .now
            }
            #if DEBUG
            print(predicate)
            #endif
            return 0
        }

        func after() {
            print(#"raw "string" with { a brace"#)
        }
    """)
    assert found == {"widgets": (1, 12), "after": (14, 16)}


def test_swift_type_and_comma_do_not_swallow_a_brace():
    found = functions("a.swift", """
        func f(_ xs: [Item]) -> [String] {
            let kinds = xs.map { $0.type }
            return Dictionary(xs.map { ($0.id, $0) }, uniquingKeysWith: { _, last in last }).keys.sorted()
        }

        func g() {
            print(1)
        }
    """)
    assert found == {"f": (1, 4), "g": (6, 8)}


def test_swift_deinit_and_subscript_are_functions():
    found = functions("a.swift", """
        final class Box {
            deinit {
                print("bye")
            }

            subscript(index: Int) -> Int {
                return index
            }
        }
    """)
    assert found == {"deinit": (2, 4), "subscript": (6, 8)}


def test_swift_get_and_set_outside_a_property_are_not_accessors():
    code = """
        func f(_ set: Set<Int>, store: Store) -> Int {
            if let stored = Store.get(id: 1) { return stored }
            for x in set {
                if x > 1 { return x }
            }
            store.set(1) { result in print(result) }
            return configure(init: 3)
        }

        func g() {
            print(1)
        }
    """
    assert functions("a.swift", code) == {"f": (1, 8), "g": (10, 12)}
    assert ccn("a.swift", code, "f") == 4


def test_swift_conditional_directive_is_not_a_branch():
    code = """
        func f() -> Int {
            #if os(iOS) && !targetEnvironment(simulator) || DEBUG
            return 1
            #else
            return 0
            #endif
        }
    """
    assert functions("a.swift", code) == {"f": (1, 7)}
    assert ccn("a.swift", code, "f") == 1


def test_swift_raw_string_with_two_hashes():
    found = functions("a.swift", """
        func f() -> String {
            return ##"a "# { quote"##
        }

        func g() {
            print(1)
        }
    """)
    assert found == {"f": (1, 3), "g": (5, 7)}


# --- through the collector ---


def test_collector_counts_a_long_kotlin_function_with_a_one_line_lambda(tmp_path):
    body = "\n".join(f"    total += {i}" for i in range(70))
    (tmp_path / "Sheet.kt").write_text(
        "fun sheet(xs: List<Int>, onDone: (Int?) -> Unit) {\n"
        "    var total = 0\n"
        "    xs.forEach { code -> if (code == 0) total = -1 else total += code }\n"
        f"{body}\n"
        "    onDone(total)\n"
        "}\n"
    )
    config = Config(root=tmp_path)
    # Stock lizard reports no function at all for this file.
    assert complexity.collect(config)["long_functions"] == 1
    assert any("sheet" in line for line in complexity.explain(config, top=5))


def test_versions_record_the_reader_revision(tmp_path):
    recorded = complexity.versions(Config(root=tmp_path))["lizard"]
    assert recorded.endswith(f"+readers{complexity.READERS_REVISION}")


def test_install_twice_wraps_the_readers_once():
    lizard_readers.install()
    lizard_readers.install()
    reader = lizard_readers.KotlinReader(lizard.FileInfoBuilder("a.kt"))
    assert [type(s) for s in reader.parallel_states] == [lizard_readers.KotlinFunctionStates]
