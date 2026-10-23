"""Snapshots for shell variable assignment and comment conversion."""

import pytest


ASSIGNMENT_CASES = [
    pytest.param('name="ChatGPT"', 'name = "ChatGPT"', id="double-quoted"),
    pytest.param("name='Argo'", 'name = "Argo"', id="single-quoted"),
    pytest.param("name=ChatGPT", 'name = "ChatGPT"', id="unquoted"),
    pytest.param("value=$name", "value = f'{name}'", id="variable-reference"),
    pytest.param(
        'value="Hello $name"',
        "value = f'Hello {name}'",
        id="interpolated-double-quoted",
    ),
    pytest.param("value=", 'value = ""', id="empty-value"),
    pytest.param(
        "value=`echo 5`",
        'value = subprocess.run(["echo", "5"], text=True, '
        "stdout=subprocess.PIPE).stdout.strip()",
        id="command-substitution",
    ),
    pytest.param(
        "INPUT_FILE=demo$1.sh",
        "INPUT_FILE = f'demo{sys.argv[1]}.sh'",
        id="command-line-arg-inside-word",
    ),
    pytest.param('x="a b"', 'x = "a b"', id="quoted-value-with-space"),
    pytest.param("x=${name}", "x = f'{name}'", id="braced-variable"),
    pytest.param("x=$1", "x = f'{sys.argv[1]}'", id="positional-arg"),
    pytest.param("x=$10", "x = f'{sys.argv[10]}'", id="multi-digit-positional"),
    pytest.param(
        'x="Value: $value"',
        "x = f'Value: {value}'",
        id="interpolated-with-prefix",
    ),
    pytest.param("x=$name.txt", "x = f'{name}.txt'", id="variable-with-suffix"),
    pytest.param("spaced =  word ", 'spaced = "word"', id="spaces-around-equals"),
    pytest.param("x = $y", "x = f'{y}'", id="spaces-with-variable"),
    pytest.param("x=\"a=b\"", 'x = "a=b"', id="equals-inside-quoted-value"),
    # KNOWN BUG: single quotes should suppress expansion but do not.
    pytest.param("x='$y'", "x = f'{y}'", id="single-quote-still-expands"),
    # KNOWN BUG: $# is not expanded, the emitted f-string is invalid Python.
    pytest.param("x=$#", "x = f'{#}'", id="argument-count-broken"),
    # KNOWN BUG: $? is not expanded, the emitted f-string is invalid Python.
    pytest.param("x=$?", "x = f'{?}'", id="last-status-broken"),
    # KNOWN BUG: inside backticks a positional parameter becomes str(<n>),
    # i.e. the literal number instead of sys.argv[n].
    pytest.param(
        "x=`echo $1`",
        'x = subprocess.run(["echo", str(1)], text=True, '
        "stdout=subprocess.PIPE).stdout.strip()",
        id="command-substitution-positional-broken",
    ),
    pytest.param(
        "x=`expr $value + 1`",
        'x = subprocess.run(["expr", str(value), "+", "1"], text=True, '
        "stdout=subprocess.PIPE).stdout.strip()",
        id="command-substitution-variable",
    ),
]


@pytest.mark.parametrize("command, expected", ASSIGNMENT_CASES)
def test_convert_assignment(transpiler, command, expected):
    assert transpiler.convert_assignment(command) == expected


def test_convert_assignment_without_equals_raises(transpiler):
    # Edge case: the dispatcher only calls this when '=' is present.
    with pytest.raises(ValueError):
        transpiler.convert_assignment("noequals")


COMMENT_CASES = [
    pytest.param("# a comment", "# a comment", id="with-hash"),
    pytest.param("  padded comment  ", "padded comment", id="stripped"),
    pytest.param("plain", "plain", id="no-hash"),
    pytest.param("", "", id="empty"),
]


@pytest.mark.parametrize("comment, expected", COMMENT_CASES)
def test_convert_comment(transpiler, comment, expected):
    assert transpiler.convert_comment(comment) == expected
