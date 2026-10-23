"""转译器前端抛出的错误类型。

所有错误都带源码位置，CLI 据此输出编译器风格的诊断信息，而不是生成一半的
Python 代码。
"""

from __future__ import annotations


class TranspileError(Exception):
    """所有面向用户的转译错误基类。"""

    stage = "transpile"

    def __init__(self, message: str, line: int = 1, col: int = 1, filename: str = "<script>"):
        self.message = message
        self.line = line
        self.col = col
        self.filename = filename
        super().__init__(self.format())

    def format(self) -> str:
        """格式化成 ``文件:行:列: 阶段 error: 信息``。"""
        return f"{self.filename}:{self.line}:{self.col}: {self.stage} error: {self.message}"


class LexError(TranspileError):
    stage = "lex"


class ParseError(TranspileError):
    stage = "parse"


class CodegenError(TranspileError):
    stage = "codegen"
