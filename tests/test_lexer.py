"""v2 词法分析器测试：引号、转义、展开、操作符和注释。"""

from __future__ import annotations

import pytest

from transpiler.errors import LexError
from transpiler.lexer import lex
from transpiler.tokens import (
    ArithmeticSegment,
    CommandSubSegment,
    LiteralSegment,
    ParameterSegment,
    TokenKind,
)


def words(source):
    return [token.word for token in lex(source) if token.kind == TokenKind.WORD]


def joined(word):
    return "".join(segment.text for segment in word.segments if isinstance(segment, LiteralSegment))


def parameters(source):
    return [
        (segment.name, segment.quoted, segment.op)
        for word in words(source)
        for segment in word.segments
        if isinstance(segment, ParameterSegment)
    ]


def ops(source):
    return [token.value for token in lex(source) if token.kind == TokenKind.OP]


def comments(source):
    return [token.value for token in lex(source) if token.kind == TokenKind.COMMENT]


def test_plain_words():
    assert [word.static_text() for word in words("echo hello world")] == ["echo", "hello", "world"]


def test_single_quotes_are_literal():
    (word,) = words("'Hello, World!'")
    segment = word.segments[0]
    assert isinstance(segment, LiteralSegment)
    assert segment.text == "Hello, World!"
    assert segment.quoted is True
    assert segment.glob is False


def test_empty_single_quotes_keep_a_word():
    (word,) = words("''")
    assert len(word.segments) == 1
    assert word.segments[0].text == ""
    assert word.segments[0].quoted is True


def test_double_quotes_split_literal_and_parameter():
    word = words('echo "My name is $name"')[1]
    assert [type(segment).__name__ for segment in word.segments] == [
        "LiteralSegment",
        "ParameterSegment",
    ]
    assert word.segments[0].text == "My name is "
    assert word.segments[0].quoted is True
    assert word.segments[1].name == "name"
    assert word.segments[1].quoted is True


def test_parameter_names_and_specials():
    assert parameters("$name $1 $# $? $$ $@ $*") == [
        ("name", False, None),
        ("1", False, None),
        ("#", False, None),
        ("?", False, None),
        ("$", False, None),
        ("@", False, None),
        ("*", False, None),
    ]


def test_braced_parameters():
    assert parameters("${name} ${1} ${10}") == [
        ("name", False, None),
        ("1", False, None),
        ("10", False, None),
    ]


def test_parameter_default_operator():
    assert parameters("${name:-fallback}") == [("name", False, ":-")]
    (word,) = words("${name:-fallback}")
    segment = word.segments[0]
    assert segment.default is not None
    assert joined(segment.default) == "fallback"


def test_pattern_parameter_expansions():
    cases = [
        ("${name#pre}", "#", "pre", None),
        ("${name##*/}", "##", "*/", None),
        ("${name%suf}", "%", "suf", None),
        ("${name%%*.txt}", "%%", "*.txt", None),
        ("${name/old/new}", "/", "old", "new"),
        ("${name//old/new}", "//", "old", "new"),
        ("${name/old}", "/", "old", ""),
        ("${name#}", "#", "", None),
    ]
    for source, operator, pattern, replacement in cases:
        (word,) = words(source)
        segment = word.segments[0]
        assert isinstance(segment, ParameterSegment)
        assert segment.op == operator
        assert segment.default is not None
        assert joined(segment.default) == pattern
        if replacement is None:
            assert segment.replacement is None
        else:
            assert segment.replacement is not None
            assert joined(segment.replacement) == replacement


def test_pattern_with_quoted_or_escaped_slash():
    (word,) = words(r"${name/a\/b/x}")
    segment = word.segments[0]
    assert joined(segment.default) == "a/b"
    assert joined(segment.replacement) == "x"

    (word,) = words('${name/"a/b"/x}')
    segment = word.segments[0]
    assert joined(segment.default) == "a/b"
    assert joined(segment.replacement) == "x"


def test_plain_positional_ten_is_one_digit_plus_literal_zero():
    # POSIX 规定 $10 是 ${1} 后面跟一个字面量 0。
    (word,) = words("$10")
    assert isinstance(word.segments[0], ParameterSegment)
    assert word.segments[0].name == "1"
    assert isinstance(word.segments[1], LiteralSegment)
    assert word.segments[1].text == "0"


def test_escaped_space_is_one_word():
    (word,) = words(r"a\ b")
    assert [type(segment).__name__ for segment in word.segments] == [
        "LiteralSegment",
        "LiteralSegment",
        "LiteralSegment",
    ]
    assert word.segments[1].text == " "
    assert word.segments[1].quoted is True


def test_escaped_dollar_is_literal():
    (word,) = words(r"\$x")
    assert word.segments[0].text == "$"
    assert word.segments[0].quoted is True
    assert not any(isinstance(segment, ParameterSegment) for segment in word.segments)


def test_command_substitution_and_backticks():
    dollar = words("$(echo hi)")[0]
    backtick = words("`echo hi`")[0]
    assert isinstance(dollar.segments[0], CommandSubSegment)
    assert dollar.segments[0].source == "echo hi"
    assert isinstance(backtick.segments[0], CommandSubSegment)
    assert backtick.segments[0].source == "echo hi"


def test_command_substitution_with_nested_parentheses():
    (word,) = words('$(python -c "print(1)")')
    assert isinstance(word.segments[0], CommandSubSegment)
    assert word.segments[0].source == 'python -c "print(1)"'


def test_arithmetic_expansion():
    (word,) = words("$((1 + 2 * (3 + 4)))")
    segment = word.segments[0]
    assert isinstance(segment, ArithmeticSegment)
    assert segment.source == "1 + 2 * (3 + 4)"


def test_quoted_expansions_are_marked_quoted():
    word = words('"$name $(echo hi) $((1+2))"')[0]
    assert all(getattr(segment, "quoted", False) for segment in word.segments)


def test_operators():
    assert ops("ls && echo ok || echo no | wc -l") == ["&&", "||", "|"]
    assert ops("cat <in >out 2>err 2>&1") == ["<", ">", "2>", "2>&1"]
    assert ops("echo hi >&2") == [">&2"]
    assert ops("a; b ;; c") == [";", ";;"]


def test_parameter_length_expansion():
    (word,) = words("${#name}")
    segment = word.segments[0]
    assert isinstance(segment, ParameterSegment)
    assert segment.name == "name"
    assert segment.op == "length"


def test_comments_and_quoting():
    assert comments("echo hi # comment") == [" comment"]
    assert comments("echo 'a # b' # tail") == [" tail"]
    assert comments("# whole line") == [" whole line"]


def test_hash_inside_word_is_literal():
    assert [word.static_text() for word in words("echo a#b")] == ["echo", "a#b"]


def test_line_continuation_joins_word():
    result = words("echo a\\\nb")
    assert [word.static_text() for word in result][0] == "echo"
    assert joined(result[1]) == "ab"


def test_newline_tokens():
    tokens = lex("echo a\necho b\n")
    assert sum(1 for token in tokens if token.kind == TokenKind.NEWLINE) == 2


def test_lone_dollar_is_literal():
    (word,) = words("$")
    assert isinstance(word.segments[0], LiteralSegment)
    assert word.segments[0].text == "$"


@pytest.mark.parametrize(
    "source",
    [
        "'unterminated",
        '"unterminated',
        "$(echo hi",
        "$((1 + 2)",
        "${name",
        "`echo hi",
    ],
)
def test_unterminated_constructs_raise_lex_error(source):
    with pytest.raises(LexError):
        lex(source)


def test_background_job_is_rejected():
    with pytest.raises(LexError, match="background"):
        lex("sleep 1 &")


def test_here_document_is_rejected_explicitly():
    with pytest.raises(LexError, match="here-documents"):
        lex("cat <<EOF\n")


def test_case_fallthrough_operator_is_rejected_explicitly():
    with pytest.raises(LexError, match="fall-through"):
        lex("case x in a) : ;& esac")
