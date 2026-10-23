"""End-to-end snapshots for ``Transpiler.transpile``.

Each case is a complete dash-like script and the exact Python text the current
implementation produces.  Note that the output intentionally preserves the
implementation's odd indentation/trailing whitespace; those are part of the
snapshot.
"""

import pytest


HEADER = (
    "#!/usr/bin/env python3\n"
    "import sys\n"
    "import glob\n"
    "import os\n"
    "import subprocess\n"
)


TRANSPILE_CASES = [
    pytest.param("", HEADER, id="empty-script"),
    pytest.param("   \n\n", HEADER, id="whitespace-only-script"),
    pytest.param(
        "#!/bin/dash\necho hello\n",
        HEADER + "\nprint(f'hello')\n    ",
        id="echo",
    ),
    pytest.param(
        '#!/bin/dash\nname="ChatGPT"\necho "My name is $name"\n',
        HEADER
        + '\nname = "ChatGPT"\n    \nprint(f\'My name is {name}\')\n    ',
        id="assignment-then-echo",
    ),
    pytest.param(
        "#!/bin/dash\n# setup\necho hi # trailing\n",
        HEADER + "\n  # setup\n    \nprint(f'hi')  # trailing\n    ",
        id="standalone-and-inline-comment",
    ),
    pytest.param(
        "#!/bin/dash\nvalue=5\n"
        "if [ $value -eq 5 ]; then\n"
        'echo "five"\n'
        "elif [ $value -eq 6 ]; then\n"
        'echo "six"\n'
        "else\n"
        'echo "other"\n'
        "fi\n",
        HEADER
        + '\nvalue = "5"\n    \n'
        "if int(value) == 5:\n"
        "    value=int(value)\n"
        "    print(f'five')\n"
        "        \n"
        "elif int(value) == 6:\n"
        "        value=int(value)\n"
        "    print(f'six')\n"
        "        \n"
        "else:\n"
        "        \n"
        "    print(f'other')\n"
        "        ",
        id="if-elif-else",
    ),
    pytest.param(
        "#!/bin/dash\nfor i in 1 2 3; do\necho $i\ndone\n",
        HEADER + "\nfor i in ['1', '2', '3']:\n\n    print(f'{i}')\n        ",
        id="for-loop",
    ),
    pytest.param(
        "#!/bin/dash\nvalue=0\n"
        "while [ $value -lt 3 ]; do\n"
        "echo $value\n"
        "value=`expr $value + 1`\n"
        "done\n",
        HEADER
        + '\nvalue = "0"\n    \n'
        "while int(value) < 3:\n"
        "    value=int(value)\n"
        "    print(f'{value}')\n"
        "        \n"
        '    value = subprocess.run(["expr", str(value), "+", "1"], text=True, '
        "stdout=subprocess.PIPE).stdout.strip()\n"
        "        ",
        id="while-loop",
    ),
    pytest.param(
        "#!/bin/dash\ncd ..\nread value\nexit 0\n",
        HEADER + "\nos.chdir('..')\n    \nvalue = input()\n    \nsys.exit(0)\n    ",
        id="cd-read-exit",
    ),
    pytest.param(
        "#!/bin/dash\nls -l\n",
        HEADER + '\nsubprocess.run(["ls", "-l"])\n    ',
        id="generic-command",
    ),
    pytest.param(
        "\n\n#!/bin/dash\n\necho a\n\n\necho b\n\n",
        HEADER + "\nprint(f'a')\n    \nprint(f'b')\n    ",
        id="blank-lines-collapsed",
    ),
    pytest.param(
        "echo hi\n",
        HEADER + "\nprint(f'hi')\n    ",
        id="no-shebang",
    ),
    pytest.param(
        "#!/bin/dash\nif [ -f x ]; then\nthen\nfi\n",
        HEADER + "\nif os.path.isfile('x'):\n    ",
        id="then-and-fi-lines-ignored",
    ),
    pytest.param(
        "#!/bin/dash\n# just a comment\n",
        HEADER + "\n  # just a comment\n    ",
        id="comment-only",
    ),
    pytest.param(
        "#!/bin/dash\necho $#\n",
        HEADER + "\nprint(f'{len(sys.argv) - 1}')\n    ",
        id="argument-count",
    ),
    # CURRENT QUIRK: only "#!/bin/dash" is skipped; another shebang becomes a comment.
    pytest.param(
        "#!/bin/sh\necho hi\n",
        HEADER + "\n  # !/bin/sh\n    \nprint(f'hi')\n    ",
        id="other-shebang-becomes-comment",
    ),
    # CURRENT QUIRK: the dispatcher's regexes require a trailing space, so a
    # bare keyword is routed to the generic-command handler.
    pytest.param(
        "#!/bin/dash\necho\n",
        HEADER + '\nsubprocess.run(["echo", ])\n    ',
        id="bare-echo-is-command",
    ),
    pytest.param(
        "#!/bin/dash\nexit\n",
        HEADER + '\nsubprocess.run(["exit", ])\n    ',
        id="bare-exit-is-command",
    ),
    pytest.param(
        "#!/bin/dash\ncd\n",
        HEADER + '\nsubprocess.run(["cd", ])\n    ',
        id="bare-cd-is-command",
    ),
    pytest.param(
        "#!/bin/dash\nread\n",
        HEADER + '\nsubprocess.run(["read", ])\n    ',
        id="bare-read-is-command",
    ),
    # README limitation: redirection is emitted as ordinary echo operands.
    pytest.param(
        "#!/bin/dash\necho hello > out.txt\n",
        HEADER + "\nprint(f'hello', f'>', f'out.txt')\n    ",
        id="redirection-unsupported",
    ),
    # README limitation: && is emitted as ordinary echo operands.
    pytest.param(
        "#!/bin/dash\nls && echo hi\n",
        HEADER + "\nprint(f'ls', f'&&', f'echo', f'hi')\n    ",
        id="logical-and-unsupported",
    ),
    # README limitation: $((...)) arithmetic is emitted as plain words.
    pytest.param(
        "#!/bin/dash\necho $((1 + 2))\n",
        HEADER + "\nprint(f'$((1', f'+', f'2))')\n    ",
        id="arithmetic-unsupported",
    ),
    # README limitation: case is emitted as a generic command.
    pytest.param(
        "#!/bin/dash\ncase $x in\n",
        HEADER + '\nsubprocess.run(["case", x, "in"])\n    ',
        id="case-unsupported",
    ),
    # CURRENT QUIRK: elif/else do not raise the indent level, so the generated
    # block is not valid Python.  Snapshot only; rewrite should fix this.
    pytest.param(
        "#!/bin/dash\nelif [ -f x ]; then\necho hi\n",
        HEADER + "\nelif os.path.isfile('x'):\n    \nprint(f'hi')\n    ",
        id="elif-without-if-quirk",
    ),
    pytest.param(
        "#!/bin/dash\nelse\necho hi\n",
        HEADER + "\nelse:\n    \nprint(f'hi')\n    ",
        id="else-without-if-quirk",
    ),
    pytest.param(
        "#!/bin/dash\nfor i in 1 2\ndo\necho $i\ndone\n",
        HEADER + "\nfor i in ['1', '2']:\n\n    print(f'{i}')\n        ",
        id="for-loop-standalone-do",
    ),
    pytest.param(
        "#!/bin/dash\nfor f in *.sh; do\necho $f\ndone\n",
        HEADER + "\nfor f in sorted(glob.glob('*.sh')):\n\n    print(f'{f}')\n        ",
        id="for-loop-glob",
    ),
    pytest.param(
        "#!/bin/dash\nx=0\nwhile [ $x -lt 2 ]\ndo\necho $x\ndone\n",
        HEADER
        + '\nx = "0"\n    \nwhile int(x) < 2:\n    x=int(x)\n    \n'
        "    print(f'{x}')\n        ",
        id="while-loop-standalone-do",
    ),
    pytest.param(
        "#!/bin/dash\nif test -f x; then\necho yes\nfi\n",
        HEADER + "\nif os.path.isfile('x'):\n    \n    print(f'yes')\n        ",
        id="if-test-keyword",
    ),
    pytest.param(
        '#!/bin/dash\nname="ChatGPT" # person\necho "hi $name"\n',
        HEADER + '\nname = "ChatGPT"  # person\n    \nprint(f\'hi {name}\')\n    ',
        id="assignment-with-inline-comment",
    ),
    # CURRENT QUIRK: any line containing '=' is treated as an assignment before
    # the generic-command branch is considered.
    pytest.param(
        "#!/bin/dash\nenv FOO=bar\n",
        HEADER + '\nenv FOO = "bar"\n    ',
        id="env-assignment-misclassified",
    ),
    # Integration snapshot covering comments, assignment, echo, if and for.
    pytest.param(
        "#!/bin/dash\n# demo\nname=\"Argo\"\necho \"Hello, $name\"\n"
        "if [ -f file ]; then\necho found\nfi\n"
        "for i in 1 2; do\necho $i\ndone\n",
        HEADER
        + "\n  # demo\n    \nname = \"Argo\"\n    \nprint(f'Hello, {name}')\n    \n"
        "if os.path.isfile('file'):\n    \n    print(f'found')\n        \n"
        "for i in ['1', '2']:\n\n    print(f'{i}')\n        ",
        id="mixed-program",
    ),
]


@pytest.mark.parametrize("script, expected", TRANSPILE_CASES)
def test_transpile(transpiler, script, expected):
    assert transpiler.transpile(script) == expected


def test_transpile_unsupported_condition_raises(transpiler):
    # README limitation: -n is not implemented and custom convert_test returns
    # a bare string, so transpile() fails while unpacking the tuple.
    script = '#!/bin/dash\nif [ -n "$x" ]; then\necho yes\nfi\n'
    with pytest.raises(ValueError):
        transpiler.transpile(script)


def test_transpile_output_starts_with_header_and_keeps_single_blank_line(transpiler):
    # Header/blank-line behaviour is shared by every successful transpile.
    output = transpiler.transpile("#!/bin/dash\necho a\necho b\n")
    assert output.startswith(HEADER)
    assert output.count("import subprocess") == 1
    assert "print(f'a')\n" in output
    assert "print(f'b')\n" in output
