# Archived v1 implementation

This folder is the original `transpile-dash-to-python` project, kept unchanged as a
reference and regression baseline. It was archived when v2 was started.

Contents:

| Path | What it is |
|---|---|
| `trans.py` | the v1 single-file regex/line-rewriting transpiler |
| `py/test_*.py` | v1 generated-output snapshots (despite the `test_` names, these are **generated Python**, not pytest tests) |
| `sh/test_*.sh` | v1 differential harnesses that compare `dash` output with transpiled Python |
| `demoRun.sh`, `test01.sh` | v1 demo/comparison scripts |
| `README.md` | v1 README |
| `tests/` | the 208-case characterization suite written for v1; it imports `legacy/trans.py` |

The v1 suite still runs:

```bash
python -m pytest legacy/tests -q     # 208 passed
```

Do not add new features here. The v2 implementation lives in the repository root
(`trans.py`, `transpiler/`, `tests/`). Keep this folder until the v2 behavior is considered
stable, then delete it or move it to a separate branch/tag.
