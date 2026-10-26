"""v2 语法分析器测试：命令、控制流、test 表达式和重定向。"""

from __future__ import annotations

import pytest

from transpiler.ast import (
    AndOr,
    BreakCommand,
    CaseCommand,
    Comment,
    ContinueCommand,
    ForCommand,
    IfCommand,
    SetCommand,
    SimpleCommand,
    TestAnd,
    TestBinary,
    TestBool,
    TestNot,
    TestOr,
    TestUnary,
    WhileCommand,
)
from transpiler.errors import ParseError
from transpiler.parser import parse


def command(source):
    node = parse(source).body[0]
    assert isinstance(node, AndOr)
    return node.first.commands[0]


def script(source):
    return parse(source).body


def test_simple_command_words():
    cmd = command("echo hello world")
    assert isinstance(cmd, SimpleCommand)
    assert [word.static_text() for word in cmd.words] == ["echo", "hello", "world"]
    assert cmd.assignments == []
    assert cmd.redirects == []


def test_assignment_only():
    cmd = command('name="Argo"')
    assert isinstance(cmd, SimpleCommand)
    assert cmd.words == []
    assert cmd.assignments[0].name == "name"
    assert cmd.assignments[0].value.segments[0].text == "Argo"


def test_prefix_assignment_before_command():
    cmd = command('FOO=bar python -c "pass"')
    assert [assignment.name for assignment in cmd.assignments] == ["FOO"]
    assert cmd.words[0].static_text() == "python"


def test_redirections():
    cmd = command("python x.py <in >out 2>>err 2>&1")
    assert [redirect.op for redirect in cmd.redirects] == ["<", ">", "2>>", "2>&1"]


def test_and_or_chain():
    node = parse("a && b || c").body[0]
    assert [op for op, _ in node.rest] == ["&&", "||"]


def test_pipeline():
    node = parse("a | b | c").body[0]
    assert len(node.first.commands) == 3


def test_if_elif_else():
    node = script(
        "if [ $x -eq 1 ]; then\necho one\nelif [ $x -eq 2 ]; then\necho two\nelse\necho other\nfi"
    )[0].first.commands[0]
    assert isinstance(node, IfCommand)
    assert len(node.branches) == 2
    assert len(node.else_body) == 1


def test_if_condition_is_a_test_expression():
    node = script("if [ $x -eq 1 ]; then echo one; fi")[0].first.commands[0]
    assert isinstance(node, IfCommand)
    test = node.branches[0][0].first.commands[0].test
    assert isinstance(test, TestBinary)
    assert test.op == "-eq"


def test_while_and_until():
    while_node = script("while [ -f x ]; do echo y; done")[0].first.commands[0]
    until_node = script("until [ -f x ]; do echo y; done")[0].first.commands[0]
    assert isinstance(while_node, WhileCommand)
    assert while_node.until is False
    assert isinstance(until_node, WhileCommand)
    assert until_node.until is True


def test_for_with_list():
    node = script("for i in 1 2 3; do echo $i; done")[0].first.commands[0]
    assert isinstance(node, ForCommand)
    assert node.var == "i"
    assert [word.static_text() for word in node.words] == ["1", "2", "3"]


def test_for_without_in_uses_positional_parameters():
    node = script("for i; do echo $i; done")[0].first.commands[0]
    assert isinstance(node, ForCommand)
    assert node.words is None


def test_case_patterns_and_bodies():
    node = script("case $x in\na|b) echo ab;;\n*) echo other;;\nesac")[0].first.commands[0]
    assert isinstance(node, CaseCommand)
    assert len(node.items) == 2
    assert [word.static_text() for word in node.items[0][0]] == ["a", "b"]
    assert [word.static_text() for word in node.items[1][0]] == ["*"]


def test_test_keyword_form():
    node = script("if test -f x; then echo y; fi")[0].first.commands[0]
    test = node.branches[0][0].first.commands[0].test
    assert isinstance(test, TestUnary)
    assert test.op == "-f"


def test_test_logical_operators():
    node = script('if [ -f a -a ! -d b -o -z "$c" ]; then echo y; fi')[0].first.commands[0]
    test = node.branches[0][0].first.commands[0].test
    assert isinstance(test, TestOr)
    assert isinstance(test.left, TestAnd)
    assert isinstance(test.left.right, TestNot)


def test_test_parentheses():
    node = script('if [ \\( -f a -o -f b \\) -a -n "$c" ]; then echo y; fi')[0].first.commands[0]
    test = node.branches[0][0].first.commands[0].test
    assert isinstance(test, TestAnd)
    assert isinstance(test.left, TestOr)


def test_empty_test_is_false():
    node = script("if [ ]; then echo y; fi")[0].first.commands[0]
    test = node.branches[0][0].first.commands[0].test
    assert isinstance(test, TestBool)
    assert test.value is False


def test_comments_are_preserved():
    body = script("# top\necho hi # inline\n")
    assert isinstance(body[0], Comment)
    assert body[0].text == "top"
    assert body[1].comment == "inline"


@pytest.mark.parametrize(
    "source, message",
    [
        ("if true; then echo x", "fi"),
        ("if true; echo x; fi", "then"),
        ("while true; do echo x", "done"),
        ("for i in 1 2; do echo $i", "done"),
        ("case x in a) echo a;;", "esac"),
        ("then", "reserved word"),
        ("foo() { echo hi; }", "function"),
        ("for ((i=0; i<2; i++)); do echo $i; done", "arithmetic for"),
        ("[ -f x", "closing ']'"),
        ("if [ -f x ]]; then echo y; fi", "closing ']'"),
        ("if [ a b ]; then echo y; fi", "unexpected test argument"),
        ("echo hi ;;", "outside a case branch"),
        ("while true; do break 2; done", "loop level"),
    ],
)
def test_parse_errors(source, message):
    with pytest.raises(ParseError) as error:
        parse(source)
    assert message in str(error.value)


def test_break_and_continue_nodes():
    """循环体里的 break/continue 解析成独立 AST 节点。"""
    loop = script("while true; do\nbreak\ncontinue\ndone")[0].first.commands[0]
    assert isinstance(loop, WhileCommand)
    break_command = loop.body[0].first.commands[0]
    continue_command = loop.body[1].first.commands[0]
    assert isinstance(break_command, BreakCommand)
    assert isinstance(continue_command, ContinueCommand)
    assert (break_command.line, break_command.col) == (2, 1)


def test_command_nodes_carry_source_position():
    """AST 命令节点保存行列号，供代码生成阶段报错使用。"""
    commands = [
        parse("echo one\necho two").body[1].first.commands[0],
        parse("if true; then :; fi").body[0].first.commands[0],
        parse("for i in 1; do :; done").body[0].first.commands[0],
    ]
    assert [(command.line, command.col) for command in commands] == [(2, 1), (1, 1), (1, 1)]


def test_set_errexit_forms():
    for source, expected in [
        ("set -e", True),
        ("set +e", False),
        ("set -o errexit", True),
        ("set +o errexit", False),
    ]:
        command = script(source)[0].first.commands[0]
        assert isinstance(command, SetCommand)
        assert command.errexit is expected


def test_compound_command_redirections():
    while_node = script("while read line; do echo $line; done < input.txt")[0].first.commands[0]
    if_node = script("if true; then echo yes; fi < input.txt")[0].first.commands[0]
    assert isinstance(while_node, WhileCommand)
    assert [redirect.op for redirect in while_node.redirects] == ["<"]
    assert isinstance(if_node, IfCommand)
    assert [redirect.op for redirect in if_node.redirects] == ["<"]
