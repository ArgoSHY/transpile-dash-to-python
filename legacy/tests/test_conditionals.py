"""Snapshots for test/if/elif/else/while condition conversion.

``convert_test`` is the single translation engine behind ``convert_if``,
``convert_elif`` and ``convert_while``.  It returns ``(python_condition,
optional_assignment)`` for supported conditions, but returns a bare string
(a comment) for unsupported ones -- the tuple-unpacking callers then raise
``ValueError``.
"""

import pytest


TEST_CASES = [
    # Numeric comparisons: literal / variable / variable-variable.
    pytest.param("[ 1 -eq 1 ]", ("1 == 1:", ""), id="eq-literals"),
    pytest.param("[ $x -eq 5 ]", ("int(x) == 5:", "x=int(x)"), id="eq-variable"),
    pytest.param("[ $x -eq $y ]", ("int(x) == int(y):", "x, y = int(x), int(y)"), id="eq-two-variables"),
    pytest.param("[ $x -ne 3 ]", ("int(x) != 3:", "x=int(x)"), id="ne"),
    pytest.param("[ $x -gt 3 ]", ("int(x) > 3:", "x=int(x)"), id="gt"),
    pytest.param("[ $x -ge 3 ]", ("int(x) >= 3:", "x=int(x)"), id="ge"),
    pytest.param("[ $x -lt 3 ]", ("int(x) < 3:", "x=int(x)"), id="lt"),
    pytest.param("[ $x -le 3 ]", ("int(x) <= 3:", "x=int(x)"), id="le"),
    pytest.param(
        "[ $x -eq $y -eq 0 ]",
        ("int(x) == int(y):", "x, y = int(x), int(y)"),
        id="extra-operand-ignored",
    ),
    # Script arguments and argument count.
    pytest.param("[ $# -eq 0 ]", ("len(sys.argv) - 1 == 0:", ""), id="argument-count"),
    # KNOWN BUG: the assignment half is not valid Python (sys.argv[1] = ...).
    pytest.param(
        "[ $1 -eq 5 ]",
        ("int(sys.argv[1]) == 5:", "sys.argv[1]=int(sys.argv[1])"),
        id="positional-arg-broken-assignment",
    ),
    pytest.param(
        '[ "$1" -eq 5 ]',
        ("int(sys.argv[1]) == 5:", "sys.argv[1]=int(sys.argv[1])"),
        id="quoted-positional-arg-broken-assignment",
    ),
    # String comparisons.
    pytest.param('[ "$a" = "$b" ]', ("a == b:", ""), id="string-equals"),
    pytest.param("[ foo = bar ]", ("'foo' == 'bar':", ""), id="string-equals-literals"),
    pytest.param("[ foo != bar ]", ("'foo' != 'bar':", ""), id="string-not-equals"),
    # File tests.
    pytest.param("test -r file", ("os.access('file', os.R_OK):", ""), id="readable"),
    pytest.param('[ -r "file name" ]', ("os.access('file name', os.R_OK):", ""), id="readable-quoted-path"),
    pytest.param("test -d dir", ("os.path.isdir('dir'):", ""), id="directory"),
    pytest.param("test -s file", ("os.path.getsize('file') > 0:", ""), id="non-empty-file"),
    pytest.param("test -f file", ("os.path.isfile('file'):", ""), id="regular-file"),
    pytest.param("test -x file", ("os.access('file', os.X_OK):", ""), id="executable"),
    pytest.param("test -w file", ("os.access('file', os.W_OK):", ""), id="writable"),
    pytest.param("test -h link", ("os.path.islink('link'):", ""), id="symlink-h"),
    pytest.param("test -L link", ("os.path.islink('link'):", ""), id="symlink-L"),
    pytest.param("test -G file", ("os.stat('file').st_gid == os.getgid():", ""), id="group-id"),
    pytest.param("test -O file", ("os.stat('file').st_uid == os.getuid():", ""), id="user-id"),
    pytest.param('test -z "$str"', ("len(str) == 0:", ""), id="zero-length"),
    # "test" keyword form and "[ ... ]" form produce the same result.
    pytest.param("test 1 -eq 1", ("1 == 1:", ""), id="test-keyword-form"),
    # CURRENT QUIRK: operator detection is substring based, so "-r" in the
    # right-hand operand hijacks the file-readable branch.
    pytest.param(
        '[ "$a" = "-r" ]',
        ("os.access('', os.R_OK):", ""),
        id="substring-operator-mismatch",
    ),
    # Unsupported tests return a bare comment string instead of a 2-tuple.
    pytest.param('[ -n "$x" ]', '# Unsupported test condition: -n "$x"', id="unsupported-n"),
    pytest.param("[ -e file ]", "# Unsupported test condition: -e file", id="unsupported-e"),
    pytest.param("[ $x ]", "# Unsupported test condition: $x", id="unsupported-bare"),
]


@pytest.mark.parametrize("command, expected", TEST_CASES)
def test_convert_test(transpiler, command, expected):
    assert transpiler.convert_test(command) == expected


IF_CASES = [
    pytest.param(
        "if [ $value -eq 5 ]; then",
        ("if int(value) == 5:", "value=int(value)"),
        id="numeric-bracket",
    ),
    pytest.param(
        "if test $value -eq 5; then",
        ("if int(value) == 5:", "value=int(value)"),
        id="numeric-test-keyword",
    ),
    pytest.param("if [ -f file ]; then", ("if os.path.isfile('file'):", ""), id="file"),
    pytest.param('if [ -z "$str" ]; then', ("if len(str) == 0:", ""), id="zero-length"),
    pytest.param('if [ "$a" = "$b" ]; then', ("if a == b:", ""), id="string-equals"),
    pytest.param('if [ "$a" != "$b" ]; then', ("if a != b:", ""), id="string-not-equals"),
    pytest.param("if [ $a -lt 3 ]; then", ("if int(a) < 3:", "a=int(a)"), id="less-than"),
    pytest.param("if [ -r file ]; then", ("if os.access('file', os.R_OK):", ""), id="readable"),
]


@pytest.mark.parametrize("command, expected", IF_CASES)
def test_convert_if(transpiler, command, expected):
    assert transpiler.convert_if(command) == expected


def test_convert_if_unsupported_condition_raises(transpiler):
    # convert_test returns a bare comment string, so tuple unpacking blows up.
    with pytest.raises(ValueError):
        transpiler.convert_if("if [ foo ]; then")


ELIF_CASES = [
    pytest.param(
        "elif [ $value -eq 6 ]; then",
        ("elif int(value) == 6:", "value=int(value)"),
        id="numeric",
    ),
    pytest.param("elif [ -d dir ]; then", ("elif os.path.isdir('dir'):", ""), id="directory"),
]


@pytest.mark.parametrize("command, expected", ELIF_CASES)
def test_convert_elif(transpiler, command, expected):
    assert transpiler.convert_elif(command) == expected


ELSE_CASES = [
    pytest.param("else", "else:", id="plain"),
    # CURRENT QUIRK: everything after "else" is discarded.
    pytest.param("else # x", "else:", id="with-trailing-text"),
]


@pytest.mark.parametrize("command, expected", ELSE_CASES)
def test_convert_else(transpiler, command, expected):
    assert transpiler.convert_else(command) == expected


WHILE_CASES = [
    pytest.param(
        "while [ $value -lt 3 ]; do",
        ("while int(value) < 3:", "value=int(value)"),
        id="numeric",
    ),
]


@pytest.mark.parametrize("command, expected", WHILE_CASES)
def test_convert_while(transpiler, command, expected):
    assert transpiler.convert_while(command) == expected


def test_convert_while_unsupported_condition_raises(transpiler):
    with pytest.raises(ValueError):
        transpiler.convert_while("while [ -e file ]; do")
