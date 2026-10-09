"""lizard with Kotlin and Swift readers that find where functions start and end.

lizard 1.24's readers for both languages lose track of the braces on everyday
code. A function whose closing brace is never seen is silently missing from the
report, and one closed by the wrong brace is measured too short or too long (on
one app: 300 of 1,641 Kotlin functions with a block body missing, 35 of them
among the 72 longer than 60 lines; in Swift 70 missing and 47 mismeasured).

What the stock readers get wrong, and what these do instead:

- Both: `type` is read as Go's keyword and the token after a comma as a name to
  skip, so a brace next to either is swallowed. Neither is special here.
- Both: an accessor name opens a function also where it is a call
  (`map.get(key)`, `defaults.set(1, forKey: k)`, `.init(x)`), a label
  (`foo(init: 3)`) or a modifier (`private(set)`). It opens one only where an
  accessor can stand and its body follows.
- Kotlin: a lambda arrow (`{ x -> ... }`) opens an "(anonymous)" function that
  then waits for the next `{`. Lambdas belong to the function they are written
  in, as closures do in Swift.
- Kotlin: an expression body (`fun f() = ...`) is read up to the closing brace
  of whatever encloses it. It ends where the expression ends.
- Kotlin: an extension receiver (`fun String.f()`) and a declaration without a
  body (`abstract fun f()`) leave a function open for good, and a name in
  backticks with spaces is not one token.
- Kotlin: an interface is skipped whole. Its functions with a body count.
- Swift: `#available`, `#Predicate`, `#if`... put the tokenizer in C macro mode,
  which swallows the rest of the line, braces included. Failable initializers
  (`init?`) are not seen.

Known limits, all rare: a Kotlin expression body is ended by a line break, so
one whose line breaks after an infix function (`a shl` / `1`) is cut short and
`fun a() = 1; fun b() = 2` on one line reads `b` inside `a`; a Kotlin call
`set(x) { ... }` to a function of that name reads as an accessor.

Run as `python -m quality_ratchet.lizard_readers <lizard args>`.
"""

from __future__ import annotations

import lizard
from lizard_languages.kotlin import KotlinReader, KotlinStates
from lizard_languages.swift import SwiftReader, SwiftStates

# A line break ends a Kotlin expression body unless the line before ends, or
# the new line starts, with something that cannot stand there on its own:
# `val x = a +` / `b`, or `foo()` / `.bar()`.
_CONDITION = "(condition)"  # stands for the `)` closing `if (...)`: its branch follows
_CONTINUES_AFTER = frozenset(
    ["=", ".", "?:", "+", "-", "*", "/", "%", "&&", "||", ",", "->", "==", "!=", "===", "!==",
     "<", "<=", ">=", "in", "is", "as", "as?", "else", ":", "::", "..", "by", "or", "and", "xor",
     "try", "do", _CONDITION]
)
_CONTINUES_WITH = frozenset([".", "?", "?:", "&&", "||", "else", "as", "as?", "::", "->", "catch", "finally"])
_CONDITION_KEYWORDS = frozenset(["if", "while", "for"])

# After a Kotlin parameter list these cannot be part of a return type or a
# `where` clause: the declaration has no body.
_NEXT_DECLARATION = frozenset(
    ["fun", "val", "var", "}", "class", "object", "interface", "abstract", "override", "private", "public",
     "protected", "internal", "open", "companion", "enum", "sealed", "data", "typealias", "const", "lateinit",
     "inline", "operator", "infix", "tailrec", "external", "expect", "actual", "init", "constructor"]
)
_OPENING = frozenset(["(", "["])
_CLOSING = frozenset([")", "]"])

_SWIFT_ACCESSORS = frozenset(["get", "set", "willSet", "didSet"])
_SWIFT_INITIALIZERS = frozenset(["init", "init?", "init!", "subscript"])
# What a Swift accessor can follow: the brace opening the property (None: it
# is the first token its block's machine sees), the brace closing the accessor
# before it, a modifier, or an attribute's arguments.
_BEFORE_SWIFT_ACCESSOR = frozenset([None, "}", ")", "mutating", "nonmutating", "consuming", "borrowing"])
_SWIFT_CONDITIONAL_DIRECTIVES = frozenset(["#if", "#elseif"])


class KotlinFunctionStates(KotlinStates):
    def __init__(self, context, in_when_cases=False, expression_body=False):
        super().__init__(context, in_when_cases)
        # True for the machine reading an expression body: it stops at the end
        # of the expression instead of at a closing brace.
        self._expression_body = expression_body
        self._depth = 0
        self._condition_open = False
        self._previous = "="
        self._previous_line = context.current_line
        self.unread = None  # the token that ended the expression: not part of it
        self._line = self._line_before = context.current_line
        self._when_subject_depth = 0

    def __call__(self, token, reader=None):
        self._line_before, self._line = self._line, self.context.current_line
        if self._expression_body:
            previous = token
            if self._state == self._state_global:  # not inside a block of the expression
                if self._ends_expression(token):
                    self.unread = token
                    return True
                if token in _OPENING:
                    if self._depth == 0:
                        self._condition_open = self._previous in _CONDITION_KEYWORDS
                    self._depth += 1
                elif token in _CLOSING:
                    self._depth -= 1
                    if self._depth == 0 and self._condition_open:
                        previous = _CONDITION
            self._previous, self._previous_line = previous, self.context.current_line
        return super().__call__(token, reader)

    def _ends_expression(self, token):
        if self._depth > 0:
            return False
        if token == "}":
            return True
        if self.context.current_line == self._previous_line:
            return False
        return self._previous not in _CONTINUES_AFTER and token not in _CONTINUES_WITH

    def statemachine_before_return(self):
        # The file ends inside an expression body: nothing came after it to end it.
        body = self._state
        if isinstance(body, KotlinFunctionStates) and body._expression_body:
            body.statemachine_before_return()
            self.context.end_of_function()
            self._state = self._state_global

    def _starts_declaration(self, token):
        # An annotation starts a declaration only on a line of its own:
        # `fun f(): @Composable () -> Unit {` has one in its return type.
        return token in _NEXT_DECLARATION or (token.startswith("@") and self._line != self._line_before)

    def _state_global(self, token):
        if token in ("get", "set"):
            # Not after a dot (a call) nor in an expression body, where no
            # accessor can stand.
            if self.last_token not in (".", "::") and not self._expression_body:
                self._accessor = token
                self._state = self._accessor_parameters
        elif token == "->" and not self._in_when_cases:
            pass  # a lambda's arrow: the lambda is part of the function around it
        elif token in ("type", "interface", ","):
            # `type` is Go's keyword, an ordinary name here. An interface is
            # read like a class: its functions with a body count. And what
            # follows a comma is not a name to skip: it can be a lambda.
            pass
        else:
            super()._state_global(token)

    def _accessor_parameters(self, token):
        if token == "(":
            self.next(self._accessor_parameter_list, token)
        else:  # `private set`, a variable named `get`...
            self.next(self._state_global, token)

    @KotlinStates.read_inside_brackets_then("()", "_accessor_body")
    def _accessor_parameter_list(self, token):
        pass

    def _accessor_body(self, token):
        if token == ":":
            self._state = self._accessor_type
        else:
            self._accessor_type(token)

    def _accessor_type(self, token):
        if token in ("{", "="):
            self.context.push_new_function(self._accessor)
            self.next(self._expect_function_impl, token)
        elif self._state != self._accessor_type or self._starts_declaration(token):
            self.next(self._state_global, token)  # it was a call, or has no body

    def _function_name(self, token):
        if token == "interface":  # `fun interface`: a type, not a function
            self._discard_function(token)
        else:
            return super()._function_name(token)

    def _expect_function_dec(self, token):
        if token == ".":  # extension receiver: the name follows
            self.context.add_to_function_name(token)
            self._state = self._function_name
        elif token in ("(", "<", "["):
            super()._expect_function_dec(token)
        elif not token.startswith("<"):  # `<String?>` is one token to lizard
            self._discard_function(token)

    def _expect_function_impl(self, token):
        if token == "{":
            self.next(self._function_impl, token)
        elif token == "=":
            self._read_expression_body()
        elif self._starts_declaration(token):
            self._discard_function(token)

    def _read_expression_body(self):
        body = self.__class__(self.context, expression_body=True)

        def callback():
            function = self.context.current_function
            # lizard counts a token before the reader sees it, so the one that
            # ended the body was counted into this function: when it starts a
            # later line, its line and its branch go back to the enclosing one.
            moved_line = self.context.current_line != body._previous_line
            moved_branch = body.unread in KotlinReader._control_flow_keywords
            if moved_line:
                function.nloc -= 1
                function.end_line = body._previous_line
            if moved_branch:
                function.cyclomatic_complexity -= 1
            self.context.end_of_function()
            self.context.current_function.nloc += moved_line
            self.context.current_function.cyclomatic_complexity += moved_branch
            self.next(self._state_global, body.unread)

        self.sub_state(body, callback)

    def _discard_function(self, token):
        """Not a function with a body after all: forget it and read `token` again."""
        forgive = self.context.forgive  # a pending `#lizard forgive` is for a real function
        self.context.forgive = True
        self.context.end_of_function()
        self.context.forgive = forgive
        self.next(self._state_global, token)

    def _when_cases(self, token):
        def callback():
            self.context.add_condition(inc=-1)
            self.next(self._state_global)

        # The subject can hold a lambda (`when (xs.first { it > 0 }) {`): the
        # cases open with the first brace outside its parentheses.
        self._when_subject_depth += (token == "(") - (token == ")")
        if token == "{" and self._when_subject_depth == 0:
            self.sub_state(self.__class__(self.context, in_when_cases=True), callback)


class SwiftFunctionStates(SwiftStates):
    def __call__(self, token, reader=None):
        # `#if os(iOS) && DEBUG` is not a branch of the function around it.
        # Every machine up the nesting sees the token: only the innermost acts.
        if not isinstance(self._state, SwiftStates):
            if token in _SWIFT_CONDITIONAL_DIRECTIVES:
                self.context.directive_line = self.context.current_line
            elif token in ("&&", "||") and self.context.current_line == self.context.directive_line:
                self.context.add_condition(inc=-1)
        return super().__call__(token, reader)

    def _state_global(self, token):
        if token in ("type", ","):
            pass  # as in Kotlin: an ordinary name, and no name to skip
        elif token in _SWIFT_ACCESSORS:
            if self.last_token in _BEFORE_SWIFT_ACCESSOR:
                self._accessor = token
                self._state = self._accessor_start
        elif token in _SWIFT_INITIALIZERS:
            if self.last_token not in (".", "(", ","):  # not `Foo.init(x)` nor a label
                self.context.push_new_function("")
                self.next(self._function_name, token)
        elif token != "deinit" or self.last_token != ".":
            super()._state_global(token)

    def _accessor_start(self, token):
        if token == "(":  # `set(newValue) {`
            self.next(self._accessor_parameter, token)
        elif token not in ("async", "throws"):
            self._accessor_block(token)

    @SwiftStates.read_inside_brackets_then("()", "_accessor_block")
    def _accessor_parameter(self, token):
        pass

    def _accessor_block(self, token):
        if token == "{":
            self.context.push_new_function(self._accessor)
            self.next(self._function_impl, token)
        else:  # a call, `private(set)`, a variable with that name...
            self.next(self._state_global, token)


_original_kotlin_tokens = KotlinReader.generate_tokens
_original_swift_tokens = SwiftReader.generate_tokens
_installed = False


def _kotlin_tokens(source_code, addition="", token_class=None):
    return _original_kotlin_tokens(source_code, r"|`[^`\n]+`" + addition, token_class)


def _swift_tokens(source_code, addition="", token_class=None):
    # A raw string or a `#directive` is one token: a lone `#` starts a C macro.
    raw_strings = r'|\#\#\".*?\"\#\#' + r'|\#\"\"\".*?\"\"\"\#' + r'|\#\"[^\n]*?\"\#'
    return _original_swift_tokens(source_code, raw_strings + r"|\#\w+" + addition, token_class)


def install() -> None:
    """Makes lizard read Kotlin and Swift with the states above. Idempotent."""
    global _installed
    if _installed:
        return
    _installed = True
    lizard.FileInfoBuilder.directive_line = 0  # line of the last Swift `#if`
    for reader, states, tokens in (
        (KotlinReader, KotlinFunctionStates, _kotlin_tokens),
        (SwiftReader, SwiftFunctionStates, _swift_tokens),
    ):
        _use(reader, states)
        reader.generate_tokens = staticmethod(tokens)


def _use(reader, states) -> None:
    original = reader.__init__

    def init(self, context):
        original(self, context)
        self.parallel_states = [states(context)]

    reader.__init__ = init


if __name__ == "__main__":
    install()
    lizard.main()
