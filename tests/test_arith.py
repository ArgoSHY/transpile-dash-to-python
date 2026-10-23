"""shell 算术表达式翻译器测试。"""

from __future__ import annotations

import pytest

from transpiler.arith import translate
from transpiler.errors import CodegenError


def evaluate(source, variables=None):
    expression = translate(source)
    values = dict(variables or {})

    def _int(name):
        text = str(name)
        if text.isdigit():
            return int(values.get(text, text))
        return int(values.get(text, 0))

    return eval(expression, {"__builtins__": {"int": int, "bool": bool}}, {"_int": _int})


def test_exact_translation_simple():
    assert translate("1 + 2") == "((1) + (2))"


def test_exact_translation_comparison():
    assert translate("x > 3") == "int((_int('x')) > (3))"


@pytest.mark.parametrize(
    "source, expected",
    [
        ("1 + 2 * 3", 7),
        ("(1 + 2) * 3", 9),
        ("10 / 3", 3),
        ("10 % 3", 1),
        ("2 ** 4", 16),
        ("1 << 3", 8),
        ("16 >> 2", 4),
        ("6 & 3", 2),
        ("6 | 3", 7),
        ("6 ^ 3", 5),
        ("-5 + 2", -3),
        ("!0", 1),
        ("!5", 0),
        ("~0", -1),
        ("1 < 2", 1),
        ("2 <= 2", 1),
        ("3 > 4", 0),
        ("3 >= 3", 1),
        ("3 == 3", 1),
        ("3 != 3", 0),
        ("1 && 1", 1),
        ("1 && 0", 0),
        ("0 || 2", 1),
        ("0 || 0", 0),
        ("1 ? 10 : 20", 10),
        ("0 ? 10 : 20", 20),
        ("010 + 1", 9),
        ("0x10 + 1", 17),
    ],
)
def test_evaluation(source, expected):
    assert evaluate(source) == expected


def test_variables():
    assert evaluate("x * (y + 1)", {"x": 3, "y": 4}) == 15


def test_positional_parameter_in_arithmetic():
    assert evaluate("$1 + $2", {"1": 5, "2": 7}) == 12


def test_argument_count_in_arithmetic():
    assert evaluate("$# - 1", {"#": 3}) == 2


@pytest.mark.parametrize(
    "source",
    ["", "   ", "1 +", "x *", "1 @ 2", "$", "1 ? 2"],
)
def test_invalid_arithmetic_raises(source):
    with pytest.raises(CodegenError):
        translate(source)
