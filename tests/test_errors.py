"""不支持的结构必须显式报错，并带上错误类型和源码位置。"""

from __future__ import annotations

import pytest

from transpiler import transpile
from transpiler.errors import CodegenError, LexError, ParseError, TranspileError


@pytest.mark.parametrize(
    "source, expected_type, message",
    [
        ("sleep 1 &", LexError, "background"),
        ('echo "unterminated', LexError, "unterminated"),
        ("echo $(echo hi", LexError, "unterminated"),
        ("echo $((1 + 2)", LexError, "arithmetic"),
        ("echo ${name", LexError, "parameter expansion"),
        ("cat <<EOF", LexError, "here-documents"),
        ("case x in a) : ;& esac", LexError, "fall-through"),
        ("foo() { echo hi; }", ParseError, "function"),
        ("for ((i=0; i<2; i++)); do echo $i; done", ParseError, "arithmetic for"),
        ("if true; then echo x", ParseError, "fi"),
        ("if true; echo x; fi", ParseError, "then"),
        ("while true; do echo x", ParseError, "done"),
        ("case x in a) echo a;;", ParseError, "esac"),
        ("then", ParseError, "reserved word"),
        ("cd / | cat", CodegenError, "pipeline"),
        ("read 1bad", CodegenError, "identifier"),
        ("x=$(if true; then echo x; fi)", CodegenError, "command substitution"),
        ("if true; then echo x; fi && echo y", CodegenError, "&&"),
        ("break", CodegenError, "outside a loop"),
        ("continue", CodegenError, "outside a loop"),
        ("shift 1 2", CodegenError, "at most one argument"),
    ],
)
def test_unsupported_constructs_raise_typed_errors(source, expected_type, message):
    with pytest.raises(expected_type) as error:
        transpile(source)
    assert message in str(error.value)


def test_error_includes_filename_line_and_column():
    with pytest.raises(ParseError) as error:
        transpile("echo ok\nfoo() { :; }\n", filename="demo.sh")
    text = str(error.value)
    assert text.startswith("demo.sh:2:")
    assert "parse error" in text


def test_transpile_error_is_the_common_base():
    with pytest.raises(TranspileError):
        transpile("sleep 1 &")


def test_unknown_redirection_target_is_rejected():
    with pytest.raises(ParseError, match="redirection"):
        transpile("echo hi >")


def test_missing_closing_bracket_is_rejected():
    with pytest.raises(ParseError, match="closing ']"):
        transpile("if [ -f x; then echo y; fi")


def test_codegen_error_reports_the_command_position():
    """代码生成错误也要带上具体命令的行列号。"""
    with pytest.raises(CodegenError) as error:
        transpile("echo ok\ncd / | cat\n", filename="demo.sh")
    assert str(error.value).startswith("demo.sh:2:1:")
