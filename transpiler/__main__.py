"""支持 ``python -m transpiler``（与 ``python trans.py`` 等价）。"""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
