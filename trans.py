#!/usr/bin/env python3
"""命令行入口：``python trans.py script.sh``（实现见 transpiler/cli.py）。"""

from __future__ import annotations

import sys

from transpiler.cli import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
