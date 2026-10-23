"""把 shell 脚本编译成 Python 源码：前端解析 + 代码生成。"""

from __future__ import annotations

from .codegen import CodeGenerator
from .parser import parse
from .runtime import PRELUDE

HEADER = "#!/usr/bin/env python3\n# 由 transpile-dash-to-python v2 生成，请勿手工修改。\n"
BODY_MARKER = "# --- 以下为生成的程序 ---\n"


def _normalise_source(source: str) -> str:
    """统一换行/编码，并去掉 shell shebang 行。"""
    source = source.lstrip("\ufeff")
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    # 生成结果自带 Python shebang，shell 的 shebang 不属于程序语义，直接去掉。
    if source.startswith("#!"):
        newline = source.find("\n")
        source = "" if newline == -1 else source[newline + 1 :]
    return source


def compile_source(source: str, filename: str = "<script>", include_runtime: bool = True) -> str:
    """解析并生成完整 Python 程序；``include_runtime=False`` 时只返回语句部分。"""
    script = parse(_normalise_source(source), filename)
    generator = CodeGenerator(filename)
    body = generator.generate(script)
    if not include_runtime:
        return body
    return HEADER + PRELUDE + "\n" + BODY_MARKER + body


__all__ = ["compile_source", "HEADER", "BODY_MARKER"]
