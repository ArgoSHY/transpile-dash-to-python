"""Snapshots for for-loop conversion."""

import pytest


FOR_CASES = [
    pytest.param(
        "for i in 1 2 3; do",
        "for i in ['1', '2', '3']:\n",
        id="number-list",
    ),
    pytest.param(
        "for i in a b c",
        "for i in ['a', 'b', 'c']:\n",
        id="word-list-without-do",
    ),
    pytest.param(
        "for f in *.sh; do",
        "for f in sorted(glob.glob('*.sh')):\n",
        id="glob",
    ),
    # CURRENT QUIRK: $@ is not expanded into sys.argv, it becomes a one-item list.
    pytest.param("for i in $@; do", "for i in ['$@']:\n", id="all-args-not-expanded"),
    pytest.param(
        "for i in 1 2 3; do ",
        "for i in ['1', '2', '3']:\n",
        id="trailing-space",
    ),
    # README limitation: $() command substitution is not tokenised as one word.
    pytest.param(
        "for x in $(seq 1 3); do",
        "for x in ['$(seq', '1', '3)']:\n",
        id="command-substitution-broken",
    ),
    # README limitation: C-style for headers are not supported.
    pytest.param(
        "for ((i=0; i<3; i++)); do",
        "for ((i=0; in ['i++))']:\n",
        id="c-style-broken",
    ),
]


@pytest.mark.parametrize("command, expected", FOR_CASES)
def test_convert_for(transpiler, command, expected):
    assert transpiler.convert_for(command) == expected
