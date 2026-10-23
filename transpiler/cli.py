"""``trans.py`` 与 ``python -m transpiler`` 共用的命令行入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import TranspileError, transpile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trans.py",
        description="Transpile a dash-like shell script into a standalone Python program.",
    )
    parser.add_argument("script", nargs="?", default="-", help="input script (default: stdin)")
    parser.add_argument("-o", "--output", help="write the generated program to this file")
    parser.add_argument(
        "--check",
        action="store_true",
        help="also compile the generated Python to verify that it is syntactically valid",
    )
    parser.add_argument(
        "--body-only",
        action="store_true",
        help="omit the runtime prelude (useful for tests/inspection)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="transpile-dash-to-python 2.0.0",
    )
    return parser


def main(argv=None) -> int:
    """处理命令行参数，返回进程退出码。"""
    # 生成结果里有中文注释，统一用 UTF-8 输出，避免 Windows 控制台/管道按
    # 本地代码页编码导致下游读取失败。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    args = build_parser().parse_args(argv)
    try:
        if args.script in (None, "-"):
            source = sys.stdin.read()
            filename = "<stdin>"
        else:
            path = Path(args.script)
            source = path.read_text(encoding="utf-8")
            filename = str(path)
    except OSError as error:
        print(f"trans.py: {error}", file=sys.stderr)
        return 2

    try:
        output = transpile(source, filename=filename, include_runtime=not args.body_only)
    except TranspileError as error:
        print(error, file=sys.stderr)
        return 2

    if args.check:
        try:
            compile(output, filename, "exec")
        except SyntaxError as error:
            print(f"{filename}: generated Python is invalid: {error}", file=sys.stderr)
            return 2

    if args.output:
        with Path(args.output).open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(output)
    else:
        sys.stdout.write(output)
        sys.stdout.flush()
    return 0


__all__ = ["build_parser", "main"]
