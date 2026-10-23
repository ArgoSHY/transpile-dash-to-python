"""支持子集的 shell 词法分析器。

词法器只负责切词，不做任何求值：把源码变成 WORD / 操作符 / 换行 / 注释 token。
每个 WORD 由若干片段组成，保留“是否带引号”这一关键信息，后面才能正确区分
字段分割、glob 展开和保留字判断。
"""

from __future__ import annotations

import re

from .errors import LexError
from .tokens import (
    ArithmeticSegment,
    CommandSubSegment,
    LiteralSegment,
    ParameterSegment,
    Segment,
    Token,
    TokenKind,
    Word,
)

# 长操作符必须排在前面，否则 "2>&1" 会被 "2>" 抢先匹配。
OPERATORS = (
    "2>&1",
    "1>&2",
    "&>>",
    "2>>",
    "1>>",
    "2>&",
    "1>&",
    "&>",
    ">>",
    "&&",
    "||",
    ";;",
    "2>",
    "1>",
    "|",
    ";",
    "(",
    ")",
    "<",
    ">",
)

SPECIAL_PARAMETERS = "#?$@*!-"

_WORD_BREAK = " \t\r\n|&;()<>"
_WORD_STOP = " \t\r\n|&;()<>'\"\\$`"
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PARAM_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*|\d+|[@*#?$!-])")
_DEFAULT_OPS = (":-", ":=", ":+", ":?", "-", "=", "+", "?")


class Lexer:
    def __init__(self, source: str, filename: str = "<script>"):
        self.source = source
        self.filename = filename
        self.pos = 0
        self.line = 1
        self.col = 1

    # ------------------------------------------------------------------ 基础工具
    def _peek(self, offset: int = 0) -> str:
        index = self.pos + offset
        return self.source[index] if 0 <= index < len(self.source) else ""

    def _advance(self) -> str:
        ch = self.source[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _error(self, message: str, line: int | None = None, col: int | None = None) -> LexError:
        return LexError(message, line or self.line, col or self.col, self.filename)

    # ------------------------------------------------------------------ token 化
    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        while self.pos < len(self.source):
            ch = self._peek()
            if ch in " \t\r":
                self._advance()
                continue
            if ch == "\\" and self._peek(1) == "\n":
                self._advance()
                self._advance()
                continue
            if ch == "\n":
                line, col = self.line, self.col
                self._advance()
                tokens.append(Token(TokenKind.NEWLINE, line=line, col=col))
                continue
            if ch == "#":
                line, col = self.line, self.col
                text = self._scan_comment()
                tokens.append(Token(TokenKind.COMMENT, value=text, line=line, col=col))
                continue
            line, col = self.line, self.col
            # 明确拒绝两个容易“看起来像但语义很复杂”的语法，避免后面报奇怪的错。
            if self.source.startswith("<<", self.pos):
                raise self._error("here-documents ('<<') are not supported")
            if self.source.startswith((";;&", ";&"), self.pos):
                raise self._error("case fall-through operators (';&', ';;&') are not supported")
            operator = self._match_operator()
            if operator is not None:
                tokens.append(Token(TokenKind.OP, value=operator, line=line, col=col))
                continue
            if ch == "&":
                raise self._error("background jobs ('&') are not supported")
            word = self._scan_word()
            tokens.append(Token(TokenKind.WORD, word=word, line=line, col=col))
        tokens.append(Token(TokenKind.EOF, line=self.line, col=self.col))
        return tokens

    def _scan_comment(self) -> str:
        self._advance()  # 消费 '#'
        chars: list[str] = []
        while self.pos < len(self.source) and self._peek() != "\n":
            chars.append(self._advance())
        return "".join(chars)

    def _match_operator(self) -> str | None:
        for op in OPERATORS:
            if self.source.startswith(op, self.pos):
                for _ in op:
                    self._advance()
                return op
        return None

    # ------------------------------------------------------------------ 单词
    def _scan_word(self) -> Word:
        line, col = self.line, self.col
        segments: list[Segment] = []
        while self.pos < len(self.source):
            ch = self._peek()
            if ch in _WORD_BREAK:
                break
            if ch == "'":
                segments.append(LiteralSegment(self._scan_single_quoted(), quoted=True))
                continue
            if ch == '"':
                segments.extend(self._scan_double_quoted())
                continue
            if ch == "\\":
                self._advance()
                if self.pos >= len(self.source):
                    segments.append(LiteralSegment("\\", quoted=True))
                    break
                nxt = self._peek()
                if nxt == "\n":
                    self._advance()
                    continue
                self._advance()
                segments.append(LiteralSegment(nxt, quoted=True))
                continue
            if ch == "$":
                segments.extend(self._scan_dollar(quoted=False))
                continue
            if ch == "`":
                segments.append(self._scan_backtick(quoted=False))
                continue
            # 一段连续的普通未加引号字符，其中的 glob 字符保持有效。
            chars: list[str] = []
            while self.pos < len(self.source):
                c = self._peek()
                if c in _WORD_STOP:
                    break
                chars.append(self._advance())
            if not chars:
                # 防御性分支：遇到意料之外的字符也至少前进一格，避免死循环。
                chars.append(self._advance())
            segments.append(LiteralSegment("".join(chars), quoted=False, glob=True))
        if not segments:
            segments.append(LiteralSegment("", quoted=True))
        return Word(tuple(segments), line=line, col=col)

    def _scan_single_quoted(self) -> str:
        line, col = self.line, self.col
        self._advance()  # 开引号
        chars: list[str] = []
        while self.pos < len(self.source):
            ch = self._advance()
            if ch == "'":
                return "".join(chars)
            chars.append(ch)
        raise LexError("unterminated single quote", line, col, self.filename)

    def _scan_double_quoted(self) -> list[Segment]:
        line, col = self.line, self.col
        self._advance()  # 开引号
        segments: list[Segment] = []
        buffer: list[str] = []

        def flush() -> None:
            if buffer:
                segments.append(LiteralSegment("".join(buffer), quoted=True))
                buffer.clear()

        while self.pos < len(self.source):
            ch = self._peek()
            if ch == '"':
                self._advance()
                flush()
                break
            if ch == "\\":
                self._advance()
                if self.pos >= len(self.source):
                    break
                nxt = self._peek()
                if nxt in '$`"\\':
                    buffer.append(self._advance())
                elif nxt == "\n":
                    self._advance()
                else:
                    buffer.append("\\")
                    buffer.append(self._advance())
                continue
            if ch == "$":
                flush()
                segments.extend(self._scan_dollar(quoted=True))
                continue
            if ch == "`":
                flush()
                segments.append(self._scan_backtick(quoted=True))
                continue
            buffer.append(self._advance())
        else:
            raise LexError("unterminated double quote", line, col, self.filename)
        if not segments:
            segments.append(LiteralSegment("", quoted=True))
        return segments

    # ------------------------------------------------------------------ 展开
    def _scan_dollar(self, quoted: bool) -> list[Segment]:
        line, col = self.line, self.col
        self._advance()  # 消费 '$'
        if self.pos >= len(self.source):
            return [LiteralSegment("$", quoted=quoted, glob=not quoted)]
        ch = self._peek()
        if ch == "(":
            if self._peek(1) == "(":
                self._advance()
                self._advance()
                raw = self._scan_arithmetic_body(line, col)
                return [ArithmeticSegment(raw, quoted, line, col)]
            self._advance()
            raw = self._scan_paren_body(line, col)
            return [CommandSubSegment(raw, quoted, line, col)]
        if ch == "{":
            self._advance()
            raw = self._scan_braced_body(line, col)
            return [self._parse_braced(raw, quoted, line, col)]
        if ch.isdigit():
            self._advance()
            return [ParameterSegment(ch, quoted)]
        if ch in SPECIAL_PARAMETERS:
            self._advance()
            return [ParameterSegment(ch, quoted)]
        if ch.isalpha() or ch == "_":
            name = self._scan_name()
            return [ParameterSegment(name, quoted)]
        return [LiteralSegment("$", quoted=quoted, glob=not quoted)]

    def _scan_name(self) -> str:
        match = _NAME_RE.match(self.source, self.pos)
        if not match:
            return ""
        name = match.group(0)
        for _ in name:
            self._advance()
        return name

    def _scan_paren_body(self, line: int, col: int) -> str:
        """扫描 ``$( ... )`` 的内部（调用前已经消费了开头的 ``$(``）。"""
        chars: list[str] = []
        depth = 1
        in_single = False
        in_double = False
        while self.pos < len(self.source):
            ch = self._advance()
            if in_single:
                chars.append(ch)
                if ch == "'":
                    in_single = False
                continue
            if in_double:
                chars.append(ch)
                if ch == "\\":
                    if self.pos < len(self.source):
                        chars.append(self._advance())
                    continue
                if ch == '"':
                    in_double = False
                continue
            if ch == "\\":
                chars.append(ch)
                if self.pos < len(self.source):
                    chars.append(self._advance())
                continue
            if ch == "'":
                in_single = True
                chars.append(ch)
                continue
            if ch == '"':
                in_double = True
                chars.append(ch)
                continue
            if ch == "(":
                depth += 1
                chars.append(ch)
                continue
            if ch == ")":
                depth -= 1
                if depth == 0:
                    return "".join(chars)
                chars.append(ch)
                continue
            chars.append(ch)
        raise LexError("unterminated command substitution", line, col, self.filename)

    def _scan_arithmetic_body(self, line: int, col: int) -> str:
        """扫描 ``$(( ... ))`` 的内部（调用前已经消费了开头的 ``$((``）。"""
        chars: list[str] = []
        depth = 0
        while self.pos < len(self.source):
            ch = self._advance()
            if ch == "(":
                depth += 1
                chars.append(ch)
                continue
            if ch == ")":
                if depth == 0:
                    if self._peek() == ")":
                        self._advance()
                        return "".join(chars)
                    raise LexError(
                        "unterminated arithmetic expansion (expected '))')",
                        line,
                        col,
                        self.filename,
                    )
                depth -= 1
                chars.append(ch)
                continue
            chars.append(ch)
        raise LexError("unterminated arithmetic expansion", line, col, self.filename)

    def _scan_braced_body(self, line: int, col: int) -> str:
        """扫描 ``${ ... }`` 的内部（调用前已经消费了开头的 ``${``）。"""
        chars: list[str] = []
        depth = 1
        in_single = False
        in_double = False
        while self.pos < len(self.source):
            ch = self._advance()
            if in_single:
                chars.append(ch)
                if ch == "'":
                    in_single = False
                continue
            if in_double:
                chars.append(ch)
                if ch == "\\" and self.pos < len(self.source):
                    chars.append(self._advance())
                    continue
                if ch == '"':
                    in_double = False
                continue
            if ch == "\\" and self.pos < len(self.source):
                chars.append(ch)
                chars.append(self._advance())
                continue
            if ch == "'":
                in_single = True
                chars.append(ch)
                continue
            if ch == '"':
                in_double = True
                chars.append(ch)
                continue
            if ch == "{":
                depth += 1
                chars.append(ch)
                continue
            if ch == "}":
                depth -= 1
                if depth == 0:
                    return "".join(chars)
                chars.append(ch)
                continue
            chars.append(ch)
        raise LexError("unterminated parameter expansion", line, col, self.filename)

    def _parse_braced(self, raw: str, quoted: bool, line: int, col: int) -> ParameterSegment:
        match = _PARAM_RE.match(raw)
        if not match:
            raise LexError(f"unsupported parameter expansion ${{{raw}}}", line, col, self.filename)
        name = match.group(1)
        rest = raw[match.end() :]
        if not rest:
            return ParameterSegment(name, quoted=quoted)
        for op in _DEFAULT_OPS:
            if rest.startswith(op):
                default_word = self._parse_default_word(rest[len(op) :], line, col)
                return ParameterSegment(name, quoted=quoted, op=op, default=default_word)
        raise LexError(f"unsupported parameter expansion ${{{raw}}}", line, col, self.filename)

    def _parse_default_word(self, text: str, line: int, col: int) -> Word:
        """把 ``${name:-word}`` 里的默认值解析成一个逻辑单词。

        默认值里的空格先按字面保存，之后是否分词取决于它出现在什么样的外层
        引号环境中。
        """
        if not text:
            return Word((), line=line, col=col)
        tokens = Lexer(text, self.filename).tokenize()
        segments: list[Segment] = []
        first = True
        for token in tokens:
            if token.kind == TokenKind.WORD and token.word is not None:
                if not first:
                    segments.append(LiteralSegment(" ", quoted=False, glob=False))
                segments.extend(token.word.segments)
                first = False
            elif token.kind == TokenKind.NEWLINE and not first:
                segments.append(LiteralSegment(" ", quoted=False, glob=False))
        return Word(tuple(segments), line=line, col=col)

    def _scan_backtick(self, quoted: bool) -> CommandSubSegment:
        line, col = self.line, self.col
        self._advance()  # 开反引号
        chars: list[str] = []
        while self.pos < len(self.source):
            ch = self._advance()
            if ch == "`":
                return CommandSubSegment("".join(chars), quoted=quoted, line=line, col=col)
            if ch == "\\":
                if self.pos >= len(self.source):
                    break
                nxt = self._peek()
                if nxt in "`\\$":
                    chars.append(self._advance())
                else:
                    chars.append("\\")
                continue
            chars.append(ch)
        raise LexError("unterminated command substitution", line, col, self.filename)


def lex(source: str, filename: str = "<script>") -> list[Token]:
    return Lexer(source, filename).tokenize()
