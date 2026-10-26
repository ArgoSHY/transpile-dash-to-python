"""端到端执行测试：先转译，再运行生成的 Python，断言输出结果。"""

from __future__ import annotations

import sys

import pytest

PY = "'" + sys.executable + "'"


def py(word: str) -> str:
    return f"{PY} {word}"


def test_echo_literal(run_shell):
    result = run_shell("echo hello")
    assert result.returncode == 0
    assert result.stdout == "hello\n"


def test_echo_single_quotes(run_shell):
    assert run_shell("echo 'Hello, World!'").stdout == "Hello, World!\n"


def test_echo_variable(run_shell):
    result = run_shell('name="Argo"\necho "My name is $name"')
    assert result.stdout == "My name is Argo\n"


def test_echo_positional_arguments(run_shell):
    result = run_shell('echo "a=$1 b=$2"', args=("one", "two"))
    assert result.stdout == "a=one b=two\n"


def test_argument_count(run_shell):
    result = run_shell('echo "count=$#"', args=("a", "b", "c"))
    assert result.stdout == "count=3\n"


def test_all_arguments_unquoted(run_shell):
    result = run_shell("echo $@", args=("a b", "c"))
    assert result.stdout == "a b c\n"


def test_all_arguments_quoted(run_shell):
    result = run_shell('echo "$@"', args=("a b", "c"))
    assert result.stdout == "a b c\n"


def test_star_quoted(run_shell):
    result = run_shell('echo "$*"', args=("a", "b"))
    assert result.stdout == "a b\n"


def test_positional_ten_is_single_digit_plus_zero(run_shell):
    args = tuple(str(index) for index in range(1, 12))
    result = run_shell("echo $10\necho ${10}", args=args)
    assert result.stdout == "10\n10\n"


def test_echo_escaped_dollar(run_shell):
    result = run_shell(r'echo "This is a dollar sign: \$"')
    assert result.stdout == "This is a dollar sign: $\n"


def test_echo_interpretes_backslash_escapes_like_dash(run_shell):
    result = run_shell(r'echo "a\tb"')
    assert result.stdout == "a\tb\n"


def test_echo_dash_n(run_shell):
    result = run_shell("echo -n a\necho b")
    assert result.stdout == "ab\n"


def test_assignment_and_interpolation(run_shell):
    result = run_shell('name="Argo"\nlocation="UNSW"\necho "$name @ $location"')
    assert result.stdout == "Argo @ UNSW\n"


def test_command_substitution_echo(run_shell):
    result = run_shell('value=$(echo 5)\necho "value=$value"')
    assert result.stdout == "value=5\n"


def test_command_substitution_backtick(run_shell):
    result = run_shell('value=`echo 5`\necho "value=$value"')
    assert result.stdout == "value=5\n"


def test_command_substitution_external(run_shell):
    result = run_shell(
        f'value=$({py("hi.py")})\necho "[$value]"',
        files={"hi.py": "print('hi')\n"},
    )
    assert result.stdout == "[hi]\n"


def test_parameter_defaults(run_shell):
    source = (
        "unset y\n"
        'echo "${y:-d1}"\n'
        'echo "${y-d2}"\n'
        'echo "[${y:+alt}]"\n'
        'echo "[${y+alt2}]"\n'
        "y=z\n"
        'echo "${y:-d3} ${y:+alt3}"'
    )
    result = run_shell(source)
    assert result.stdout == "d1\nd2\n[]\n[]\nz alt3\n"


def test_arithmetic(run_shell):
    result = run_shell("echo $((1 + 2 * 3))\necho $((10 / 3))\necho $((2 ** 3))")
    assert result.stdout == "7\n3\n8\n"


def test_arithmetic_with_variables(run_shell):
    result = run_shell("x=5\ny=3\necho $((x * y + 1))")
    assert result.stdout == "16\n"


def test_if_elif_else(run_shell):
    result = run_shell(
        "value=5\n"
        "if [ $value -eq 5 ]; then\n"
        'echo "five"\n'
        "elif [ $value -eq 6 ]; then\n"
        'echo "six"\n'
        "else\n"
        'echo "other"\n'
        "fi"
    )
    assert result.stdout == "five\n"


def test_if_external_command_condition(run_shell):
    result = run_shell(
        f"if {py('ok.py')}; then echo ok; else echo no; fi",
        files={"ok.py": "raise SystemExit(0)\n"},
    )
    assert result.stdout == "ok\n"


def test_nested_control_flow(run_shell):
    result = run_shell(
        "if [ -f a.txt ]; then\n"
        "for i in 1 2; do\n"
        "if [ $i -eq 1 ]; then echo one; else echo two; fi\n"
        "done\n"
        "fi",
        files={"a.txt": "x"},
    )
    assert result.stdout == "one\ntwo\n"


def test_for_list(run_shell):
    assert run_shell("for i in 1 2 3; do\necho $i\ndone").stdout == "1\n2\n3\n"


def test_for_glob(run_shell):
    result = run_shell(
        "for f in *.txt; do\necho $f\ndone",
        files={"a.txt": "a", "b.txt": "b", "c.md": "c"},
    )
    assert result.stdout == "a.txt\nb.txt\n"


def test_for_positional_parameters(run_shell):
    result = run_shell('for x in "$@"; do\necho [$x]\ndone', args=("a b", "c"))
    assert result.stdout == "[a b]\n[c]\n"


def test_while_loop(run_shell):
    result = run_shell("x=0\nwhile [ $x -lt 3 ]; do\necho $x\nx=$((x + 1))\ndone")
    assert result.stdout == "0\n1\n2\n"


def test_until_loop(run_shell):
    result = run_shell("x=0\nuntil [ $x -ge 2 ]; do\nx=$((x + 1))\ndone\necho $x")
    assert result.stdout == "2\n"


def test_case_with_glob_patterns(run_shell):
    result = run_shell(
        "x=hello.txt\ncase $x in\n*.md) echo markdown;;\n*.txt) echo text;;\n*) echo other;;\nesac"
    )
    assert result.stdout == "text\n"


def test_case_without_match(run_shell):
    result = run_shell('case x in a) echo a;; b) echo b;; esac\necho "status=$?"')
    assert result.stdout == "status=0\n"


def test_test_unary_file_predicates(run_shell):
    result = run_shell(
        "if [ -f data.txt ]; then echo file; fi\n"
        "if [ -d sub ]; then echo dir; fi\n"
        "if [ -e missing ]; then echo exists; else echo absent; fi",
        files={"data.txt": "x"},
        dirs=["sub"],
    )
    assert result.stdout == "file\ndir\nabsent\n"


def test_test_numeric_and_string_comparisons(run_shell):
    result = run_shell(
        "x=5\nif [ $x -eq 5 ]; then echo eq; fi\n"
        'if [ "$x" != "6" ]; then echo ne; fi\n'
        'if [ "abc" = "abc" ]; then echo str; fi'
    )
    assert result.stdout == "eq\nne\nstr\n"


def test_test_logical_operators(run_shell):
    result = run_shell(
        "if [ -f data.txt -a ! -d missing ]; then echo yes; fi", files={"data.txt": "x"}
    )
    assert result.stdout == "yes\n"


def test_empty_test_is_false(run_shell):
    result = run_shell("if [ ]; then echo true; else echo false; fi")
    assert result.stdout == "false\n"


def test_and_or_status(run_shell):
    result = run_shell("false && echo yes || echo no\ntrue && echo ok")
    assert result.stdout == "no\nok\n"


def test_exit_code(run_shell):
    result = run_shell("echo before\nexit 3\necho after")
    assert result.returncode == 3
    assert result.stdout == "before\n"


def test_final_status_is_last_command_status(run_shell):
    assert run_shell("echo done\nfalse").returncode == 1


def test_read_from_stdin(run_shell):
    result = run_shell('echo "Enter:"\nread value\necho "You entered: $value"', stdin="hello\n")
    assert result.stdout == "Enter:\nYou entered: hello\n"


def test_read_multiple_variables(run_shell):
    result = run_shell('read a b\nread c\necho "$a|$b|$c"', stdin="one two three\nfour five\n")
    assert result.stdout == "one|two three|four five\n"


def test_redirect_stdout_and_append(run_shell):
    result = run_shell("echo hello > out.txt\necho world >> out.txt")
    assert result.stdout == ""
    assert (result.workdir / "out.txt").read_text(encoding="utf-8") == "hello\nworld\n"


def test_redirect_input(run_shell):
    result = run_shell(
        'read value < input.txt\necho "got $value"', files={"input.txt": "from-file\n"}
    )
    assert result.stdout == "got from-file\n"


def test_redirect_stderr(run_shell):
    result = run_shell(
        f"{py('noisy.py')} > out.txt 2> err.txt",
        files={"noisy.py": "import sys\nprint('out')\nprint('err', file=sys.stderr)\n"},
    )
    assert (result.workdir / "out.txt").read_text(encoding="utf-8") == "out\n"
    assert (result.workdir / "err.txt").read_text(encoding="utf-8") == "err\n"


def test_redirect_ampersand_greater(run_shell):
    result = run_shell(
        f"{py('noisy.py')} &> both.txt",
        files={"noisy.py": "import sys\nprint('out')\nprint('err', file=sys.stderr)\n"},
    )
    content = (result.workdir / "both.txt").read_text(encoding="utf-8")
    assert "out\n" in content
    assert "err\n" in content


def test_redirect_stderr_to_stdout(run_shell):
    result = run_shell(
        f"{py('noisy.py')} 2>&1",
        files={"noisy.py": "import sys\nprint('out')\nprint('err', file=sys.stderr)\n"},
    )
    # stdout/stderr 已合并，但子进程缓冲会让先后顺序不固定，只比较内容。
    assert sorted(result.stdout.splitlines()) == ["err", "out"]


def test_pipeline_external_commands(run_shell):
    result = run_shell(
        f"{py('a.py')} | {py('b.py')}",
        files={
            "a.py": "print('hello')\n",
            "b.py": "import sys\nprint(sys.stdin.read().strip().upper())\n",
        },
    )
    assert result.stdout == "HELLO\n"


def test_pipeline_with_builtin_echo(run_shell):
    result = run_shell(
        f"echo hello | {py('b.py')}",
        files={"b.py": "import sys\nprint(sys.stdin.read().strip().upper())\n"},
    )
    assert result.stdout == "HELLO\n"


def test_pipeline_python_grep_matches(run_shell):
    result = run_shell("echo hello world | grep hello")
    assert result.stdout == "hello world\n"
    assert result.returncode == 0


def test_pipeline_python_grep_no_match_sets_status(run_shell):
    result = run_shell("echo hello | grep missing")
    assert result.stdout == ""
    assert result.returncode == 1


@pytest.mark.parametrize(
    "source, expected",
    [
        ("echo HELLO | grep -i hello", "HELLO\n"),
        ("echo abc | grep -c a", "1\n"),
        ('echo "a\\nb" | grep -n a', "1:a\n"),
        ("echo abc | grep -v abc", ""),
    ],
)
def test_pipeline_python_grep_options(run_shell, source, expected):
    assert run_shell(source).stdout == expected


def test_pipeline_python_wc_lines(run_shell):
    assert run_shell("echo hello | wc -l").stdout == "1\n"
    assert run_shell('echo "a\\nb\\nc" | wc -l').stdout == "3\n"
    assert run_shell("echo -n hello | wc -l").stdout == "0\n"


def test_pipeline_python_grep_and_wc_chain(run_shell):
    result = run_shell("echo hello | grep ell | wc -l")
    assert result.stdout == "1\n"
    assert result.returncode == 0


def test_pipeline_python_grep_after_external_command(run_shell):
    result = run_shell(
        f"{py('lines.py')} | grep beta",
        files={"lines.py": "print('alpha'); print('beta')\n"},
    )
    assert result.stdout == "beta\n"


def test_pipeline_python_grep_reads_stdin_when_first(run_shell):
    result = run_shell("grep ^alpha | wc -l", stdin="alpha\nbeta\n")
    assert result.stdout == "1\n"


def test_pipeline_python_wc_after_failed_grep(run_shell):
    result = run_shell('echo hello | grep missing | wc -l\necho "status=$?"')
    assert result.stdout == "0\nstatus=0\n"


def test_pipeline_status_is_last_command(run_shell):
    result = run_shell(
        f'{py("a.py")} | {py("b.py")}\necho "status=$?"',
        files={"a.py": "raise SystemExit(0)\n", "b.py": "raise SystemExit(3)\n"},
    )
    assert result.stdout == "status=3\n"


def test_external_command_not_found(run_shell):
    result = run_shell('definitely_not_a_command_xyz\necho "status=$?"')
    assert result.stdout == "status=127\n"
    assert "command not found" in result.stderr


def test_export_sets_child_environment(run_shell):
    result = run_shell(
        f"export FOO=bar\n{py('env.py')}",
        files={"env.py": "import os\nprint(os.environ.get('FOO'))\n"},
    )
    assert result.stdout == "bar\n"


def test_unset(run_shell):
    result = run_shell('x=1\nunset x\necho "${x:-empty}"')
    assert result.stdout == "empty\n"


def test_cd_and_pwd(run_shell):
    result = run_shell("cd sub\npwd", dirs=["sub"])
    assert result.stdout.strip() == str(result.workdir / "sub")


def test_glob_with_no_matches_stays_literal(run_shell):
    result = run_shell("echo *.zzz")
    assert result.stdout == "*.zzz\n"


def test_quoted_glob_is_not_expanded(run_shell):
    result = run_shell('echo "*.py"', files={"x.py": "pass\n"})
    assert result.stdout == "*.py\n"


def test_unquoted_variable_is_field_split(run_shell):
    result = run_shell(
        f'x="a b"\n{py("args.py")} $x',
        files={"args.py": "import sys\nprint(len(sys.argv) - 1)\n"},
    )
    assert result.stdout == "2\n"


def test_quoted_variable_is_not_split(run_shell):
    result = run_shell(
        f'x="a b"\n{py("args.py")} "$x"',
        files={"args.py": "import sys\nprint(len(sys.argv) - 1)\n"},
    )
    assert result.stdout == "1\n"


def test_empty_unquoted_expansion_is_dropped(run_shell):
    result = run_shell(
        f"x=\n{py('args.py')} $x",
        files={"args.py": "import sys\nprint(len(sys.argv) - 1)\n"},
    )
    assert result.stdout == "0\n"


def test_quoted_empty_expansion_is_kept(run_shell):
    result = run_shell(
        f'x=\n{py("args.py")} "$x"',
        files={"args.py": "import sys\nprint(len(sys.argv) - 1)\n"},
    )
    assert result.stdout == "1\n"


def test_comment_and_shebang_handling(run_shell):
    result = run_shell("#!/bin/dash\n# a comment\necho hi # inline\n")
    assert result.stdout == "hi\n"


def test_crlf_input(run_shell):
    result = run_shell("echo a\r\necho b\r\n")
    assert result.stdout == "a\nb\n"


def test_empty_script(run_shell):
    result = run_shell("")
    assert result.returncode == 0
    assert result.stdout == ""


def test_nested_loops(run_shell):
    result = run_shell('for i in 1 2; do\nfor j in a b; do\necho "$i$j"\ndone\ndone')
    assert result.stdout == "1a\n1b\n2a\n2b\n"


def test_break_in_while_loop(run_shell):
    result = run_shell(
        "i=0\n"
        "while true; do\n"
        "i=$((i + 1))\n"
        "if [ $i -ge 3 ]; then break; fi\n"
        "echo $i\n"
        "done\n"
        "echo done"
    )
    assert result.stdout == "1\n2\ndone\n"


def test_break_in_for_loop(run_shell):
    result = run_shell("for i in 1 2 3 4; do\nif [ $i -eq 2 ]; then break; fi\necho $i\ndone")
    assert result.stdout == "1\n"


def test_continue_in_for_loop(run_shell):
    result = run_shell("for i in 1 2 3; do\nif [ $i -eq 2 ]; then continue; fi\necho $i\ndone")
    assert result.stdout == "1\n3\n"


def test_continue_in_while_loop(run_shell):
    result = run_shell(
        "i=0\n"
        "while [ $i -lt 4 ]; do\n"
        "i=$((i + 1))\n"
        "if [ $i -eq 2 ]; then continue; fi\n"
        "echo $i\n"
        "done"
    )
    assert result.stdout == "1\n3\n4\n"


def test_shift_updates_positional_parameters(run_shell):
    result = run_shell(
        'echo "before=$#:$1"\nshift\necho "after=$#:$1"',
        args=("a", "b"),
    )
    assert result.stdout == "before=2:a\nafter=1:b\n"


def test_shift_loop_over_all_arguments(run_shell):
    result = run_shell(
        "while [ $# -gt 0 ]; do\necho $1\nshift\ndone",
        args=("a", "b", "c"),
    )
    assert result.stdout == "a\nb\nc\n"


def test_shift_multiple_arguments(run_shell):
    result = run_shell(
        'echo "before=$#:$1"\nshift 2\necho "after=$#:$1"',
        args=("a", "b", "c"),
    )
    assert result.stdout == "before=3:a\nafter=1:c\n"


def test_shift_too_many_returns_failure_without_changing_args(run_shell):
    result = run_shell(
        'shift 5\necho "status=$? count=$# first=$1"',
        args=("a", "b"),
    )
    assert result.stdout == "status=1 count=2 first=a\n"


def test_shift_then_all_arguments(run_shell):
    result = run_shell('shift\necho "$@"', args=("a", "b"))
    assert result.stdout == "b\n"


def test_shift_invalid_count_returns_failure(run_shell):
    result = run_shell('shift nope\necho "status=$?"', args=("a",))
    assert result.stdout == "status=1\n"


def test_break_only_exits_inner_loop(run_shell):
    result = run_shell(
        "for i in 1 2; do\n"
        "for j in a b; do\n"
        'if [ "$j" = a ]; then break; fi\n'
        'echo "$i$j"\n'
        "done\n"
        "echo $i\n"
        "done"
    )
    assert result.stdout == "1\n2\n"


@pytest.mark.parametrize(
    "source, expected",
    [
        ('echo "${unsetvar:-fallback}"', "fallback\n"),
        ('echo "${unsetvar+fallback}"', "\n"),
        ('echo "${unsetvar:=assigned}"\necho "${unsetvar}"', "assigned\nassigned\n"),
    ],
)
def test_parameter_operators(run_shell, source, expected):
    assert run_shell(source).stdout == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ('x=foobar\necho "${x#foo}"', "bar\n"),
        ('x=foobar\necho "${x##*o}"', "bar\n"),
        ('p=/usr/local/bin\necho "${p#*/}"', "usr/local/bin\n"),
        ('p=/usr/local/bin\necho "${p##*/}"', "bin\n"),
        ('f=file.tar.gz\necho "${f%.gz}"', "file.tar\n"),
        ('f=file.tar.gz\necho "${f%%.*}"', "file\n"),
        ('x=foobar\necho "${x%bar}"', "foo\n"),
        ('x=foobar\necho "${x/foo/X}"', "Xbar\n"),
        ('x=foobar\necho "${x/o/0}"', "f0obar\n"),
        ('x=foobar\necho "${x//o/0}"', "f00bar\n"),
        ('x=foobar\necho "${x/foo/}"', "bar\n"),
        ('x=foobar\necho "${x#}"', "foobar\n"),
    ],
)
def test_string_pattern_expansions(run_shell, source, expected):
    assert run_shell(source).stdout == expected


def test_pattern_expansion_on_unset_variable(run_shell):
    assert run_shell('echo "[${missing#pre}]"').stdout == "[]\n"


def test_while_read_from_redirected_file(run_shell):
    result = run_shell(
        'while read line; do\necho "line:$line"\ndone < input.txt',
        files={"input.txt": "alpha\nbeta\ngamma\n"},
    )
    assert result.stdout == "line:alpha\nline:beta\nline:gamma\n"


def test_if_read_from_redirected_file(run_shell):
    result = run_shell(
        'if read x; then\necho "x=$x"\nfi < input.txt',
        files={"input.txt": "alpha\n"},
    )
    assert result.stdout == "x=alpha\n"


def test_for_loop_reads_successive_lines_from_redirect(run_shell):
    result = run_shell(
        'for i in 1 2; do\nread line\necho "$i:$line"\ndone < input.txt',
        files={"input.txt": "alpha\nbeta\n"},
    )
    assert result.stdout == "1:alpha\n2:beta\n"


def test_nested_compound_redirects_share_stdin(run_shell):
    result = run_shell(
        'while read a; do\nif read b; then\necho "$a-$b"\nfi\ndone < input.txt',
        files={"input.txt": "alpha\nbeta\ngamma\n"},
    )
    assert result.stdout == "alpha-beta\n"


def test_external_command_uses_compound_redirected_stdin(run_shell):
    result = run_shell(
        f"if true; then\n{py('readstdin.py')}\nfi < input.txt",
        files={
            "input.txt": "alpha\nbeta\n",
            "readstdin.py": "import sys\nprint(sys.stdin.read().strip().replace(chr(10), ','))\n",
        },
    )
    assert result.stdout == "alpha,beta\n"


def test_read_returns_failure_at_eof(run_shell):
    result = run_shell('read x < empty.txt\necho "status=$?"', files={"empty.txt": ""})
    assert result.stdout == "status=1\n"
