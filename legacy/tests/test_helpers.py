"""Snapshots for the two line-level helper functions.

``split_comment_from_command`` splits a source line into code + comment using
simple quote tracking, and ``remove_blank`` collapses repeated blank lines.
"""

import pytest


SPLIT_CASES = [
    pytest.param("echo hi # comment", ("echo hi", "comment"), id="inline-comment"),
    pytest.param('echo "a # b"', ('echo "a # b"', ""), id="hash-inside-double-quotes"),
    pytest.param("echo 'a # b'", ("echo 'a # b'", ""), id="hash-inside-single-quotes"),
    pytest.param(
        'echo "it\'s # fine"',
        ('echo "it\'s # fine"', ""),
        id="apostrophe-inside-double-quotes",
    ),
    # CURRENT QUIRK: any '#' outside quotes starts a comment, even glued to a word.
    pytest.param("echo hi#notcomment", ("echo hi", "notcomment"), id="hash-glued-to-word"),
    # '$#' is not a comment: the '#' is preceded by a dollar sign.
    pytest.param("echo $#", ("echo $#", ""), id="argument-count"),
    pytest.param('echo "x" # c', ('echo "x"', "c"), id="comment-after-quoted-word"),
    pytest.param("# full comment", ("", "full comment"), id="comment-only-line"),
    pytest.param("echo a # c # d", ("echo a", "c # d"), id="only-first-hash-splits"),
    pytest.param(
        'echo "unclosed # still',
        ('echo "unclosed # still', ""),
        id="unclosed-quote",
    ),
    pytest.param("cmd #", ("cmd", ""), id="empty-comment"),
    pytest.param(
        "echo $# # real comment",
        ("echo $#", "real comment"),
        id="argument-count-then-comment",
    ),
    pytest.param(
        'echo "$#" # real comment',
        ('echo "$#"', "real comment"),
        id="quoted-argument-count-then-comment",
    ),
    pytest.param("", ("", ""), id="empty-line"),
]


@pytest.mark.parametrize("line, expected", SPLIT_CASES)
def test_split_comment_from_command(transpiler, line, expected):
    assert transpiler.split_comment_from_command(line) == expected


REMOVE_BLANK_CASES = [
    pytest.param("a\n\n\nb", "a\n\nb", id="collapse-middle-blanks"),
    pytest.param("\n\na", "\na", id="collapse-leading-blanks"),
    pytest.param("a\n\n", "a\n", id="collapse-trailing-blanks"),
    pytest.param("", "", id="empty"),
    # CURRENT QUIRK: a whitespace-only line is "blank" but is kept verbatim.
    pytest.param("a\n   \nb", "a\n   \nb", id="whitespace-line-kept"),
    pytest.param("a\nb", "a\nb", id="nothing-to-remove"),
    pytest.param("a\n\n\n\nb", "a\n\nb", id="many-blanks"),
]


@pytest.mark.parametrize("text, expected", REMOVE_BLANK_CASES)
def test_remove_blank(transpiler, text, expected):
    assert transpiler.remove_blank(text) == expected
