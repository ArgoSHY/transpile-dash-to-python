"""transpile-dash-to-python v2。

对外主要接口::

    from transpiler import transpile
    python_source = transpile(shell_source)
"""

from __future__ import annotations

from .errors import CodegenError, LexError, ParseError, TranspileError
from .lexer import lex

__version__ = "2.0.0"

__all__ = [
    "transpile",
    "lex",
    "TranspileError",
    "LexError",
    "ParseError",
    "CodegenError",
    "__version__",
]


def transpile(source: str, filename: str = "<script>", include_runtime: bool = True) -> str:
    """把 dash 风格脚本转译成可直接运行的 Python 程序。"""
    from .pipeline import compile_source

    return compile_source(source, filename=filename, include_runtime=include_runtime)
