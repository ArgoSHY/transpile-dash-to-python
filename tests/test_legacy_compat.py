"""从 legacy/ 旧测试语料迁移来的兼容性测试。

这些用例覆盖旧版差分脚本想验证的语义，但直接运行生成的 Python，
因此 Windows 上也能执行。
"""

from __future__ import annotations

import sys
from pathlib import Path

PY = "'" + sys.executable + "'"


def test_simple_echo(run_shell):
    assert run_shell("echo 'Hello, World!'").stdout == "Hello, World!\n"


def test_variable_echo(run_shell):
    result = run_shell('name="Argo"\necho "My name is $name"')
    assert result.stdout == "My name is Argo\n"


def test_command_args(run_shell):
    result = run_shell('echo "The first argument is: $1"', args=("TestArg",))
    assert result.stdout == "The first argument is: TestArg\n"


def test_special_chars(run_shell):
    result = run_shell(r'echo "This is a dollar sign: \$"')
    assert result.stdout == "This is a dollar sign: $\n"


def test_variable_assignment(run_shell):
    result = run_shell('name="ChatGPT"\nvalue=`echo 5`\necho "Value is: $value"')
    assert result.stdout == "Value is: 5\n"


def test_echo_variants(run_shell):
    source = (
        "name='Argo'\n"
        'location="UNSW"\n'
        "echo  'hello' $2  '$1' '$my'  name is \"$name\" \"hello\" "
        "'space      space' \"welcome to        $location\" $# '$10' : "
        "\"This is the 'tenth' : $10\"\n"
    )
    result = run_shell(source, args=("1", "friend", "3"))
    expected = (
        "hello friend $1 $my name is Argo hello space      space "
        "welcome to        UNSW 3 $10 : This is the 'tenth' : 10\n"
    )
    assert result.stdout == expected


def test_echo_variants_full(run_shell):
    source = (
        "#!/bin/dash\n"
        "\n"
        "echo 'Hello, World!'\n"
        'name="ChatGPT"\n'
        'echo "My name is $name"\n'
        'echo "Special characters: \\$ \\\\$"\n'
        'echo "Command arguments: $1 $2"\n'
    )
    result = run_shell(source, args=("Arg1", "Arg2"))
    expected = (
        "Hello, World!\nMy name is ChatGPT\nSpecial characters: $ $\nCommand arguments: Arg1 Arg2\n"
    )
    assert result.stdout == expected


def test_conditionals(run_shell):
    source = (
        "value=5\n"
        "if [ $value -eq 5 ]; then\n"
        'echo "The value is 5"\n'
        "elif [ $value -eq 6 ]; then\n"
        'echo "The value is 6"\n'
        "else\n"
        'echo "The value is neither 5 nor 6"\n'
        "fi\n"
    )
    assert run_shell(source).stdout == "The value is 5\n"


def test_if_statement(run_shell):
    source = (
        "value=5\n"
        "if [ $value -eq 5 ]; then\n"
        'echo "The value is 5"\n'
        "else\n"
        'echo "The value is not 5"\n'
        "fi\n"
    )
    assert run_shell(source).stdout == "The value is 5\n"


def test_loops(run_shell):
    # 旧测试用外部 expr 命令；这里改成算术展开，跨平台且更稳定。
    source = (
        "for i in 1 2 3; do\n"
        "echo $i\n"
        "done\n"
        "value=0\n"
        "while [ $value -lt 3 ]; do\n"
        "echo $value\n"
        "value=$((value + 1))\n"
        "done\n"
    )
    assert run_shell(source).stdout == "1\n2\n3\n0\n1\n2\n"


def test_read_command(run_shell):
    source = 'echo "Enter a value:"\nread value\necho "You entered: $value"\n'
    assert run_shell(source, stdin="42\n").stdout == "Enter a value:\nYou entered: 42\n"


def test_exit_command(run_shell):
    result = run_shell('echo "Exiting..."\nexit 0\n')
    assert result.returncode == 0
    assert result.stdout == "Exiting...\n"


def test_cd_command(run_shell):
    result = run_shell("cd ..\npwd\n")
    assert Path(result.stdout.strip()).resolve() == result.workdir.parent.resolve()


def test_other_commands(run_shell):
    result = run_shell(
        f"{PY} hello.py\n",
        files={"hello.py": "print('external command works')\n"},
    )
    assert result.stdout == "external command works\n"


def test_read_and_echo_roundtrip(run_shell):
    result = run_shell('read x\necho "x=$x"\n', stdin="value\n")
    assert result.stdout == "x=value\n"
