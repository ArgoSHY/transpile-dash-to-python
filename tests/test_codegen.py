"""代码生成器的 golden 快照测试（只比较生成语句部分）。"""

from __future__ import annotations

import pytest

from transpiler import transpile

EXIT = "_sys.exit(_status)\n"


def body(source: str) -> str:
    return transpile(source, include_runtime=False)


CODEGEN_CASES = [
    pytest.param("", EXIT, id="empty"),
    pytest.param("echo hello", "_status = _echo(['hello'])\n" + EXIT, id="echo-literal"),
    pytest.param(
        'name="Argo"',
        "name = 'Argo'\n_status = 0\n" + EXIT,
        id="assignment",
    ),
    pytest.param(
        'echo "Hello, $1"',
        "_status = _echo(_words((('q', 'Hello, '), ('P', _arg(1)),)))\n" + EXIT,
        id="echo-parameter",
    ),
    pytest.param(
        "if [ $x -eq 5 ]; then\necho five\nelse\necho other\nfi",
        "if _test_binary('-eq', _assign((('p', _get('x')),)), '5'):\n"
        "    _status = _echo(['five'])\n"
        "else:\n"
        "    _status = _echo(['other'])\n" + EXIT,
        id="if-else",
    ),
    pytest.param(
        "for i in 1 2 3; do\necho $i\ndone",
        "for i in ['1', '2', '3']:\n    _status = _echo(_words((('p', _get('i')),)))\n" + EXIT,
        id="for-loop",
    ),
    pytest.param(
        "x=0\nwhile [ $x -lt 2 ]; do\nx=$((x+1))\ndone",
        "x = '0'\n"
        "_status = 0\n"
        "while _test_binary('-lt', _assign((('p', _get('x')),)), '2'):\n"
        "    x = _assign((('p', str(((_int('x')) + (1)))),))\n"
        "    _status = 0\n" + EXIT,
        id="while-loop",
    ),
    pytest.param(
        "case $x in\na|b) echo AB;;\n*) echo other;;\nesac",
        "_case_value = _assign((('p', _get('x')),))\n"
        "if _case_match(_case_value, ['a', 'b']):\n"
        "    _status = _echo(['AB'])\n"
        "elif _case_match(_case_value, ['*']):\n"
        "    _status = _echo(['other'])\n"
        "else:\n"
        "    _status = 0\n" + EXIT,
        id="case",
    ),
    pytest.param(
        "echo hi > out.txt\necho there >> out.txt",
        "_status = _echo(['hi'], stdout_path='out.txt', stdout_append=False)\n"
        "_status = _echo(['there'], stdout_path='out.txt', stdout_append=True)\n" + EXIT,
        id="redirect",
    ),
    pytest.param(
        "if [ -f file -a ! -d dir ]; then echo ok; fi",
        "if (_test_unary('-f', 'file') and (not _test_unary('-d', 'dir'))):\n"
        "    _status = _echo(['ok'])\n"
        "else:\n"
        "    _status = 0\n" + EXIT,
        id="test-expression",
    ),
    pytest.param(
        "false && echo yes || echo no",
        "_status = 0 if (((False and _ok(_echo(['yes']))) or _ok(_echo(['no'])))) else 1\n" + EXIT,
        id="and-or",
    ),
    pytest.param(
        "python a.py | python b.py",
        "_status = _pipeline([['python', 'a.py'], ['python', 'b.py']])\n" + EXIT,
        id="pipeline",
    ),
    pytest.param(
        'x=$(echo hi)\necho "$x"',
        "x = _assign((('p', _cmdsub_echo(['hi'])),))\n"
        "_status = 0\n"
        "_status = _echo(_words((('P', _get('x')),)))\n" + EXIT,
        id="command-substitution",
    ),
    pytest.param(
        "echo $((1 + 2 * 3))",
        "_status = _echo(_words((('p', str(((1) + (((2) * (3)))))),)))\n" + EXIT,
        id="arithmetic",
    ),
    pytest.param(
        "# top\necho hi # tail\n",
        "# top\n_status = _echo(['hi'])  # tail\n" + EXIT,
        id="comments",
    ),
    pytest.param(
        "#!/bin/dash\necho hi\n",
        "_status = _echo(['hi'])\n" + EXIT,
        id="shebang-stripped",
    ),
    pytest.param(
        "for i in 1 2; do\nbreak\ndone",
        "for i in ['1', '2']:\n    break\n" + EXIT,
        id="break-in-for",
    ),
    pytest.param(
        "while true; do\ncontinue\ndone",
        "while True:\n    continue\n" + EXIT,
        id="continue-in-while",
    ),
    pytest.param(
        "shift\nshift 2",
        "_status = _shift(1)\n_status = _shift('2')\n" + EXIT,
        id="shift",
    ),
    pytest.param(
        'while read line; do\necho "line:$line"\ndone < input.txt',
        "with open('input.txt', 'r', encoding='utf-8') as _dsh_stdin_1:\n"
        "    _stdin_stack.append(_dsh_stdin_1)\n"
        "    try:\n"
        "        while _ok(_read_vars(['line'])):\n"
        "            _status = _echo(_words((('q', 'line:'), ('P', _get('line')),)))\n"
        "    finally:\n"
        "        _stdin_stack.pop()\n" + EXIT,
        id="compound-input-redirection",
    ),
    pytest.param(
        "echo hello | grep hello | wc -l",
        "_status = _pipeline([('echo', ['hello'], True, True), "
        "('grep', ['hello']), ('wc', ['-l'])])\n" + EXIT,
        id="python-pipeline-builtins",
    ),
]


@pytest.mark.parametrize("source, expected", CODEGEN_CASES)
def test_codegen_golden(source, expected):
    assert body(source) == expected


SYNTAX_CASES = [
    "echo hello",
    'name="Argo"\necho "My name is $name"',
    "if [ -f x ]; then\nfor i in 1 2; do\necho $i\ndone\nelse\necho no\nfi",
    "x=0\nwhile [ $x -lt 3 ]; do\nx=$((x+1))\ndone",
    "case $x in\na|b) echo AB;;\n*) echo other;;\nesac",
    "python x.py < in > out 2>&1",
    "python a.py | python b.py",
    "false && echo yes || echo no",
    'echo "a\\tb"',
    "for i in 1 2; do\nif [ $i -eq 1 ]; then continue; fi\nbreak\ndone",
    "while [ $# -gt 0 ]; do\necho $1\nshift\ndone",
    "while read line; do\necho $line\ndone < input.txt",
    "echo hello | grep hello | wc -l",
]


@pytest.mark.parametrize("source", SYNTAX_CASES)
def test_generated_program_compiles(source):
    program = transpile(source)
    compile(program, "<generated>", "exec")


def test_full_program_has_header_runtime_and_marker():
    program = transpile("echo hi")
    assert program.startswith("#!/usr/bin/env python3\n")
    assert "由 transpile-dash-to-python v2 生成" in program
    assert "def _echo(" in program
    assert "# --- 以下为生成的程序 ---" in program


def test_body_only_has_no_runtime():
    output = transpile("echo hi", include_runtime=False)
    assert "_sys.exit(_status)" in output
    assert "def _echo(" not in output
