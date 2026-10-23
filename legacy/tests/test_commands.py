"""Snapshots for generic commands, cd, exit and read conversions."""

import pytest


COMMAND_CASES = [
    pytest.param("ls", 'subprocess.run(["ls", ])', id="no-arguments"),
    pytest.param("ls -l", 'subprocess.run(["ls", "-l"])', id="one-argument"),
    pytest.param(
        "python3 trans.py shell.sh",
        'subprocess.run(["python3", "trans.py", "shell.sh"])',
        id="multiple-arguments",
    ),
    pytest.param("foo bar", 'subprocess.run(["foo", "bar"])', id="word-argument"),
    pytest.param("foo $name", 'subprocess.run(["foo", name])', id="variable-argument"),
    pytest.param(
        'foo "$name"',
        'subprocess.run(["foo", name])',
        id="quoted-variable-argument",
    ),
    pytest.param(
        "foo $@",
        'subprocess.run(["foo", *sys.argv[1:]])',
        id="all-args",
    ),
    pytest.param(
        'foo "$@"',
        'subprocess.run(["foo", *sys.argv[1:]])',
        id="quoted-all-args",
    ),
    # CURRENT QUIRK: arguments are split on whitespace, so a quoted argument
    # containing a space is torn apart and the emitted code is malformed.
    pytest.param(
        'cmd "a b"',
        'subprocess.run(["cmd", ""a", "b""])',
        id="quoted-space-argument-broken",
    ),
    pytest.param(
        "  ls -la /tmp",
        'subprocess.run(["ls", "-la", "/tmp"])',
        id="leading-whitespace",
    ),
]


@pytest.mark.parametrize("command, expected", COMMAND_CASES)
def test_convert_command(transpiler, command, expected):
    assert transpiler.convert_command(command) == expected


CD_CASES = [
    pytest.param("cd ..", "os.chdir('..')", id="parent"),
    pytest.param("cd /tmp", "os.chdir('/tmp')", id="absolute-path"),
    pytest.param("cd -", "os.chdir('-')", id="previous-directory"),
    # CURRENT QUIRK: quotes are kept as part of the path.
    pytest.param(
        'cd "dir with space"',
        'os.chdir(\'"dir with space"\')',
        id="quoted-path-keeps-quotes",
    ),
    # CURRENT QUIRK: trailing whitespace is kept as part of the path.
    pytest.param("cd .. ", "os.chdir('.. ')", id="trailing-space-kept"),
]


@pytest.mark.parametrize("command, expected", CD_CASES)
def test_convert_cd(transpiler, command, expected):
    assert transpiler.convert_cd(command) == expected


def test_convert_cd_without_target_raises(transpiler):
    # The dispatcher requires "cd <path>"; a bare "cd" is not converted.
    with pytest.raises(ValueError):
        transpiler.convert_cd("cd")


EXIT_CASES = [
    pytest.param("exit 0", "sys.exit(0)", id="zero"),
    pytest.param("exit 1", "sys.exit(1)", id="one"),
    pytest.param("exit 0 ", "sys.exit(0)", id="trailing-space"),
    pytest.param("exit 1 2", "sys.exit(1)", id="extra-arguments-ignored"),
    # KNOWN BUG: the dollar is not stripped, so the generated line is invalid.
    pytest.param("exit $code", "sys.exit($code)", id="variable-code-broken"),
    # CURRENT QUIRK: splitting on a single space treats the empty field as the code.
    pytest.param("exit  1", "sys.exit(0)", id="double-space"),
]


@pytest.mark.parametrize("command, expected", EXIT_CASES)
def test_convert_exit(transpiler, command, expected):
    assert transpiler.convert_exit(command) == expected


def test_convert_exit_without_code_raises(transpiler):
    # The dispatcher requires "exit <code>"; a bare "exit" is not converted.
    with pytest.raises(IndexError):
        transpiler.convert_exit("exit")


READ_CASES = [
    pytest.param("read value", "value = input()", id="simple"),
    # CURRENT QUIRK: the -r flag is ignored and the last word is used.
    pytest.param("read -r line", "line = input()", id="dash-r-ignored"),
    # CURRENT QUIRK: only the last of several names is kept.
    pytest.param("read name extra", "extra = input()", id="last-name-wins"),
    # CURRENT QUIRK: a bare "read" names the variable "read"; the transpile
    # dispatcher actually routes bare "read" to the generic command handler.
    pytest.param("read", "read = input()", id="bare-read"),
]


@pytest.mark.parametrize("command, expected", READ_CASES)
def test_convert_read(transpiler, command, expected):
    assert transpiler.convert_read(command) == expected
