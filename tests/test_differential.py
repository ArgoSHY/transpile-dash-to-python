"""与真实 dash 的差分测试（仅 POSIX 环境运行）。

在 Linux 上比较 ``dash script.sh`` 与生成 Python 程序的 stdout 和退出码。
Windows 上的 Git dash 虽然找得到，但换行、路径和管道行为与 POSIX dash 不一致，
会产生假失败，所以整个模块在 Windows 上跳过，交给 Linux 环境/CI 验证。
"""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="differential tests need a POSIX dash; run them on Linux",
)

CASES = [
    pytest.param("echo hello", {}, id="echo-literal"),
    pytest.param('name="Argo"\necho "My name is $name"', {}, id="variable-echo"),
    pytest.param(
        'echo "args: $# $1 $2"\necho "$@"',
        {"args": ("a", "b")},
        id="arguments",
    ),
    pytest.param("echo 'single quoted' \"double quoted\"", {}, id="quoting"),
    pytest.param(r'echo "tab:\ta"', {}, id="echo-escapes"),
    pytest.param(
        "value=5\nif [ $value -eq 5 ]; then\necho five\n"
        "elif [ $value -eq 6 ]; then\necho six\nelse\necho other\nfi",
        {},
        id="if-elif-else",
    ),
    pytest.param("for i in 1 2 3; do\necho $i\ndone", {}, id="for"),
    pytest.param(
        "x=0\nwhile [ $x -lt 3 ]; do\necho $x\nx=$((x + 1))\ndone",
        {},
        id="while-arithmetic",
    ),
    pytest.param(
        "x=b\ncase $x in\na) echo A;;\nb|c) echo BC;;\n*) echo other;;\nesac",
        {},
        id="case",
    ),
    pytest.param(
        "if [ -f data.txt -a ! -d missing ]; then echo yes; else echo no; fi",
        {"files": {"data.txt": "x"}},
        id="test-file-logic",
    ),
    pytest.param(
        'if [ 3 -lt 5 -o -z "$x" ]; then echo yes; fi',
        {},
        id="test-numeric-logic",
    ),
    pytest.param("echo $((1 + 2 * 3)) $((10 / 3))", {}, id="arithmetic"),
    pytest.param('value=$(echo hi)\necho "[$value]"', {}, id="command-substitution"),
    pytest.param('read x\necho "x=$x"', {"stdin": "hello\n"}, id="read"),
    pytest.param("echo hello > out.txt\necho world >> out.txt", {}, id="redirection"),
    pytest.param(
        "for f in *.txt; do\necho $f\ndone",
        {"files": {"a.txt": "", "b.txt": ""}},
        id="glob",
    ),
    pytest.param("false && echo yes || echo no\ntrue && echo ok", {}, id="and-or"),
    pytest.param("echo before\nexit 7", {}, id="exit-status"),
    pytest.param('x="a b"\nfor y in $x; do echo "[$y]"; done', {}, id="word-splitting"),
    pytest.param("echo hello | cat", {}, id="echo-pipeline"),
    pytest.param(
        'while read line; do\necho "[$line]"\ndone < input.txt',
        {"files": {"input.txt": "alpha\nbeta\n"}},
        id="compound-redirection",
    ),
    pytest.param('echo "a\\nb\\nc" | grep b', {}, id="python-grep-pipeline"),
    pytest.param('echo "a\\nb\\nc" | wc -l', {}, id="python-wc-pipeline"),
    pytest.param("set -e\necho before\nfalse\necho after", {}, id="set-e"),
    pytest.param(
        'IFS=,\nx="a,b,c"\nfor y in $x; do echo "[$y]"; done',
        {},
        id="custom-ifs",
    ),
    pytest.param('false | true\necho "status=$?"', {}, id="pipeline-status"),
    pytest.param("echo *.nonexistent", {}, id="unmatched-glob"),
    pytest.param('echo "$(echo "a b")"', {}, id="nested-quotes"),
    pytest.param('x=hello\necho "${#x}"', {}, id="parameter-length"),
    pytest.param('x=abcdef\necho "${x:2:3}"', {}, id="substring"),
    pytest.param('set -- a b\nshift\necho "$# $1"', {}, id="set-positional"),
    pytest.param("printf '%s:%03d\\n' n 7", {}, id="printf"),
    pytest.param('false && echo "hi"\necho $?', {}, id="and-or-status"),
    pytest.param("set -e\nfalse && echo hi\necho after", {}, id="set-e-and-or"),
    pytest.param("set -e\ntrue && false\necho after", {}, id="set-e-and-or-fail"),
]


@pytest.mark.parametrize("source, kwargs", CASES)
def test_generated_program_matches_dash(run_shell, run_dash, source, kwargs):
    shell_result = run_shell(source, **kwargs)
    dash_result = run_dash(source, **kwargs)
    assert shell_result.stdout == dash_result.stdout
    assert shell_result.returncode == dash_result.returncode
