"""词法分析器产出的 Token 和单词片段（Word Segment）类型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TokenKind(Enum):
    WORD = "word"
    OP = "op"
    NEWLINE = "newline"
    COMMENT = "comment"
    EOF = "eof"


@dataclass(frozen=True, slots=True)
class LiteralSegment:
    """源码中的一段普通文本。

    ``quoted`` 为真表示这段文本来自引号或反斜杠转义，因此不参与字段分割，
    也不参与通配符展开；``glob`` 为真表示未加引号的普通文本，其中的
    ``* ? [`` 保留通配符含义。
    """

    text: str
    quoted: bool = False
    glob: bool = False


@dataclass(frozen=True, slots=True)
class ParameterSegment:
    """``$name`` / ``${name...}`` 形式的参数展开。

    ``default`` 对 ``:-``/``:=`` 等默认值运算符表示默认值；对 ``#``/``%`` 和
    ``/`` 系列表示要匹配的 pattern。``replacement`` 只用于 ``/`` / ``//``。
    """

    name: str
    quoted: bool = False
    op: str | None = None
    default: Word | None = None
    replacement: Word | None = None


@dataclass(frozen=True, slots=True)
class CommandSubSegment:
    """``$(...)`` 或反引号命令替换，源码先原样保存，代码生成时再解析。"""

    source: str
    quoted: bool = False
    line: int = 1
    col: int = 1


@dataclass(frozen=True, slots=True)
class ArithmeticSegment:
    """``$((...))`` 算术展开，源码先原样保存。"""

    source: str
    quoted: bool = False
    line: int = 1
    col: int = 1


Segment = LiteralSegment | ParameterSegment | CommandSubSegment | ArithmeticSegment


@dataclass(frozen=True, slots=True)
class Word:
    """一个 shell 单词，由若干字面量/展开片段拼接而成。"""

    segments: tuple[Segment, ...] = ()
    line: int = 1
    col: int = 1

    def static_text(self) -> str | None:
        """返回纯字面量单词的文本，动态单词返回 ``None``。

        没有片段的单词（空赋值右值）视为 ``""``。带引号的文本不算“静态”：
        ``"if"`` 不能被当成保留字 ``if``。
        """
        if not self.segments:
            return ""
        if len(self.segments) == 1:
            seg = self.segments[0]
            if isinstance(seg, LiteralSegment) and not seg.quoted:
                return seg.text
        return None

    def is_empty(self) -> bool:
        """单词是否没有任何有效内容。"""
        return not self.segments or all(
            isinstance(seg, LiteralSegment) and not seg.text and not seg.quoted
            for seg in self.segments
        )


@dataclass(frozen=True, slots=True)
class Token:
    kind: TokenKind
    value: str = ""
    word: Word | None = None
    line: int = 1
    col: int = 1

    def describe(self) -> str:
        """给错误信息用的简短描述。"""
        if self.kind == TokenKind.WORD and self.word is not None:
            static = self.word.static_text()
            return f"word {static!r}" if static is not None else "word"
        if self.kind == TokenKind.OP:
            return f"{self.value!r}"
        return self.kind.value
