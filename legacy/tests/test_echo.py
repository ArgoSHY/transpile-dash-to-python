"""Snapshots for echo conversion.

``convert_echo`` is the implementation actually wired into ``transpile()``.
``convert_echo_beta`` is an older alternate implementation that is still
present in the class but no longer called by the dispatcher ("dead code" from
the current entry point); it is snapshotted too because it is a public method
of the core class.
"""

import pytest


ECHO_CASES = [
    pytest.param("echo hello", "print(f'hello')", id="plain"),
    pytest.param("echo 'Hello, World!'", "print(f'Hello, World!')", id="single-quoted"),
    pytest.param(
        'echo "My name is $name"',
        "print(f'My name is {name}')",
        id="double-quoted-variable",
    ),
    pytest.param("echo $name", "print(f'{name}')", id="unquoted-variable"),
    pytest.param(
        'echo "Command arguments: $1 $2"',
        "print(f'Command arguments: {sys.argv[1]} {sys.argv[2]}')",
        id="positional-args",
    ),
    pytest.param("echo ${name}", "print(f'{name}')", id="braced-variable"),
    pytest.param("echo ${1}", "print(f'{sys.argv[1]}')", id="braced-positional"),
    pytest.param("echo $#", "print(f'{len(sys.argv) - 1}')", id="argument-count"),
    # CURRENT QUIRK: $@ is not expanded by convert_echo, it stays literal.
    pytest.param("echo $@", "print(f'$@')", id="all-args-not-expanded"),
    pytest.param("echo $*", "print(f'$*')", id="star-not-expanded"),
    # CURRENT QUIRK: -n is not special-cased by convert_echo, it becomes an operand.
    pytest.param("echo -n hello", "print(f'-n', f'hello')", id="dash-n-not-handled"),
    pytest.param(
        'echo "a b" \'c d\' e',
        "print(f'a b', f'c d', f'e')",
        id="mixed-quoting",
    ),
    # CURRENT QUIRK: bare "echo" is not matched by the "echo " regex, so the
    # word "echo" itself becomes the printed text.
    pytest.param("echo", "print(f'echo')", id="bare-echo"),
    pytest.param("echo ''", "print(f'')", id="empty-single-quoted"),
    pytest.param('echo "It\'s"', 'print(f"It\'s")', id="apostrophe-in-double-quotes"),
    pytest.param(
        'echo "Special characters: \\$ \\\\$"',
        "print(f'Special characters: \\$ \\\\$')",
        id="escaped-dollars",
    ),
    pytest.param("echo hello   world", "print(f'hello', f'world')", id="multiple-spaces"),
    pytest.param("   echo hi", "print(f'hi')", id="leading-whitespace"),
    pytest.param("echo\thello", "print(f'hello')", id="tab-separator"),
    # CURRENT QUIRK: convert_echo does not expand globs (convert_echo_beta does).
    pytest.param("echo *", "print(f'*')", id="glob-stays-literal"),
    pytest.param("echo $10", "print(f'{sys.argv[10]}')", id="multi-digit-positional"),
    # CURRENT QUIRK: only unquoted $# is special-cased; inside quotes it is literal.
    pytest.param('echo "$#"', "print(f'$#')", id="quoted-argument-count"),
    pytest.param(
        "echo $? $! $$",
        "print(f'$?', f'$!', f'$$')",
        id="special-shell-vars-literal",
    ),
    pytest.param('echo "x"y"z"', 'print(f\'x\', f\'y"z"\')', id="adjacent-quotes"),
    # CURRENT QUIRK: backslash-escaped $HOME is still substituted, leaving a
    # stray backslash in the generated f-string.
    pytest.param("echo \\$HOME", "print(f'\\{HOME}')", id="escaped-variable"),
    # README limitation: $((...)) arithmetic is not supported.
    pytest.param(
        "echo $((x + y))",
        "print(f'$((x', f'+', f'y))')",
        id="arithmetic-passthrough",
    ),
    # README limitation: redirection tokens are just extra echo operands.
    pytest.param(
        "echo hello >file",
        "print(f'hello', f'>file')",
        id="redirection-passthrough",
    ),
    pytest.param(
        'echo "$1  $2"',
        "print(f'{sys.argv[1]}  {sys.argv[2]}')",
        id="double-space-between-vars",
    ),
    pytest.param('echo "a" "b"', "print(f'a', f'b')", id="two-quoted-words"),
    pytest.param('echo "a b"c', "print(f'a b', f'c')", id="quote-followed-by-text"),
    pytest.param('echo "dollar: $"', "print(f'dollar: $')", id="trailing-dollar"),
]


@pytest.mark.parametrize("command, expected", ECHO_CASES)
def test_convert_echo(transpiler, command, expected):
    assert transpiler.convert_echo(command) == expected


ECHO_BETA_CASES = [
    pytest.param("echo hello", "print(f'hello')", id="plain"),
    pytest.param("echo 'Hello, World!'", "print(f'Hello, World!')", id="single-quoted"),
    pytest.param(
        'echo "My name is $name"',
        "print(f'My name is {name}')",
        id="double-quoted-variable",
    ),
    pytest.param("echo -n hi", 'print(f\'hi\', end="")', id="dash-n"),
    pytest.param("echo $@", "print(sys.argv[1:])", id="all-args"),
    pytest.param("echo *", 'print(" ".join(sorted(glob.glob("*"))))', id="glob"),
    # CURRENT QUIRK: repeated spaces are collapsed by the split/join pipeline.
    pytest.param('echo "a  b"', "print(f'a b')", id="collapses-repeated-spaces"),
    pytest.param("echo $1", "print(f'{sys.argv[1]}')", id="positional-arg"),
    pytest.param("echo ${name}", "print(f'{name}')", id="braced-variable"),
    pytest.param('echo "$1"', "print(f'{sys.argv[1]}')", id="quoted-positional-arg"),
    # KNOWN BUG: $# becomes the invalid f-string placeholder {#}.
    pytest.param("echo $#", "print(f'{#}')", id="argument-count-broken"),
    # CURRENT QUIRK: same bare-echo behaviour as convert_echo.
    pytest.param("echo", "print(f'echo')", id="bare-echo"),
    pytest.param(
        "  echo  hi  there ",
        "print(f'hi there')",
        id="trimmed-and-joined",
    ),
]


@pytest.mark.parametrize("command, expected", ECHO_BETA_CASES)
def test_convert_echo_beta(transpiler, command, expected):
    assert transpiler.convert_echo_beta(command) == expected
