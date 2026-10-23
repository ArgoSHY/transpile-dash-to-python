"""把 POSIX shell 算术 ``$((...))`` 翻译成 Python 表达式。

这里只做纯语法翻译：shell 变量变成 ``_int("name")`` 调用，比较运算包一层
``int(...)`` 以得到 0/1（和 shell 一致），整数除法映射成 ``//``。
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import CodegenError

_MULTI_OPS = ("**", "<<", ">>", "<=", ">=", "==", "!=", "&&", "||")
_SINGLE_OPS = set("+-*/%()<>!~&|^?:")
# 运算符优先级：数字越大结合越紧。
_BINARY_PRECEDENCE = {
    "||": 1,
    "&&": 2,
    "|": 3,
    "^": 4,
    "&": 5,
    "==": 6,
    "!=": 6,
    "<": 7,
    "<=": 7,
    ">": 7,
    ">=": 7,
    "<<": 8,
    ">>": 8,
    "+": 9,
    "-": 9,
    "*": 10,
    "/": 10,
    "%": 10,
    "**": 11,
}
_RIGHT_ASSOCIATIVE = {"**"}
_COMPARISON_OPS = {"==", "!=", "<", "<=", ">", ">="}
_UNARY_OPS = {"-", "+", "!", "~"}


@dataclass(frozen=True, slots=True)
class _Lexeme:
    kind: str  # 词法类型：number / name / op
    text: str


def _tokenize(source: str, filename: str, line: int, col: int) -> list[_Lexeme]:
    lexemes: list[_Lexeme] = []
    index = 0
    length = len(source)
    while index < length:
        ch = source[index]
        if ch in " \t\r\n":
            index += 1
            continue
        if ch.isdigit():
            start = index
            if source.startswith(("0x", "0X"), index):
                index += 2
                while index < length and source[index] in "0123456789abcdefABCDEF":
                    index += 1
            else:
                while index < length and source[index].isdigit():
                    index += 1
            lexemes.append(_Lexeme("number", source[start:index]))
            continue
        if ch.isalpha() or ch == "_":
            start = index
            while index < length and (source[index].isalnum() or source[index] == "_"):
                index += 1
            lexemes.append(_Lexeme("name", source[start:index]))
            continue
        if ch == "$":
            start = index
            index += 1
            if index < length and (source[index].isalnum() or source[index] == "_"):
                while index < length and (source[index].isalnum() or source[index] == "_"):
                    index += 1
            elif index < length and source[index] in "#?$@*-":
                index += 1
            else:
                raise CodegenError("empty '$' in arithmetic expression", line, col, filename)
            lexemes.append(_Lexeme("name", source[start:index]))
            continue
        matched = None
        for op in _MULTI_OPS:
            if source.startswith(op, index):
                matched = op
                break
        if matched is not None:
            lexemes.append(_Lexeme("op", matched))
            index += len(matched)
            continue
        if ch in _SINGLE_OPS:
            lexemes.append(_Lexeme("op", ch))
            index += 1
            continue
        raise CodegenError(
            f"unsupported character {ch!r} in arithmetic expression", line, col, filename
        )
    return lexemes


def _normalize_number(text: str) -> str:
    if text.lower().startswith("0x"):
        return str(int(text, 16))
    if len(text) > 1 and text.startswith("0"):
        # POSIX shell 算术里以 0 开头的整数是八进制；但 "08" 不是合法八进制，
        # 这种写法退回十进制处理，避免直接崩溃。
        try:
            return str(int(text, 8))
        except ValueError:
            return str(int(text, 10))
    return str(int(text, 10))


def _variable_expression(token: str) -> str:
    name = token[1:] if token.startswith("$") else token
    return f"_int({name!r})"


class _ArithmeticParser:
    def __init__(self, lexemes: list[_Lexeme], filename: str, line: int, col: int):
        self.lexemes = lexemes
        self.filename = filename
        self.line = line
        self.col = col
        self.index = 0

    def _peek(self) -> _Lexeme | None:
        return self.lexemes[self.index] if self.index < len(self.lexemes) else None

    def _advance(self) -> _Lexeme:
        lexeme = self.lexemes[self.index]
        self.index += 1
        return lexeme

    def _match_op(self, *ops: str) -> str | None:
        lexeme = self._peek()
        if lexeme is not None and lexeme.kind == "op" and lexeme.text in ops:
            self._advance()
            return lexeme.text
        return None

    def _expect_op(self, op: str) -> None:
        if self._match_op(op) is None:
            raise CodegenError(
                f"expected {op!r} in arithmetic expression", self.line, self.col, self.filename
            )

    def parse(self) -> str:
        expression = self._parse_ternary()
        if self._peek() is not None:
            raise CodegenError(
                f"unexpected token {self._peek().text!r} in arithmetic expression",
                self.line,
                self.col,
                self.filename,
            )
        return expression

    def _parse_ternary(self) -> str:
        condition = self._parse_binary(1)
        if self._match_op("?"):
            true_branch = self._parse_ternary()
            self._expect_op(":")
            false_branch = self._parse_ternary()
            return f"(({true_branch}) if ({condition}) else ({false_branch}))"
        return condition

    def _parse_binary(self, min_precedence: int) -> str:
        left = self._parse_unary()
        while True:
            lexeme = self._peek()
            if lexeme is None or lexeme.kind != "op":
                break
            precedence = _BINARY_PRECEDENCE.get(lexeme.text)
            if precedence is None or precedence < min_precedence:
                break
            operator = self._advance().text
            next_min = precedence if operator in _RIGHT_ASSOCIATIVE else precedence + 1
            right = self._parse_binary(next_min)
            left = self._combine(operator, left, right)
        return left

    def _parse_unary(self) -> str:
        lexeme = self._peek()
        if lexeme is not None and lexeme.kind == "op" and lexeme.text in _UNARY_OPS:
            operator = self._advance().text
            operand = self._parse_unary()
            if operator == "!":
                return f"int(not ({operand}))"
            if operator == "~":
                return f"(~({operand}))"
            return f"({operator}({operand}))"
        return self._parse_primary()

    def _parse_primary(self) -> str:
        lexeme = self._peek()
        if lexeme is None:
            raise CodegenError(
                "unexpected end of arithmetic expression", self.line, self.col, self.filename
            )
        if lexeme.kind == "number":
            self._advance()
            return _normalize_number(lexeme.text)
        if lexeme.kind == "name":
            self._advance()
            return _variable_expression(lexeme.text)
        if lexeme.text == "(":
            self._advance()
            expression = self._parse_ternary()
            self._expect_op(")")
            return f"({expression})"
        raise CodegenError(
            f"unexpected token {lexeme.text!r} in arithmetic expression",
            self.line,
            self.col,
            self.filename,
        )

    @staticmethod
    def _combine(operator: str, left: str, right: str) -> str:
        if operator in _COMPARISON_OPS:
            return f"int(({left}) {operator} ({right}))"
        if operator == "&&":
            return f"int(bool({left}) and bool({right}))"
        if operator == "||":
            return f"int(bool({left}) or bool({right}))"
        if operator == "/":
            return f"(({left}) // ({right}))"
        return f"(({left}) {operator} ({right}))"


def translate(source: str, filename: str = "<script>", line: int = 1, col: int = 1) -> str:
    """把一个 shell 算术表达式翻译成等价的 Python 表达式字符串。"""
    lexemes = _tokenize(source, filename, line, col)
    if not lexemes:
        raise CodegenError("empty arithmetic expression", line, col, filename)
    return _ArithmeticParser(lexemes, filename, line, col).parse()


__all__ = ["translate"]
