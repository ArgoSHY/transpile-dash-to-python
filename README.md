# transpile-dash-to-python v2

A small, grammar-driven transpiler from a documented **dash/POSIX-shell subset** to
standalone Python 3. It replaces the original regex/line-rewriting version (now kept in
[`legacy/`](legacy/)) with a real front end:

```
shell source
   │
   ├── lexer   transpiler/lexer.py      quotes, escapes, $var, $(...), $((...)), operators
   ├── parser  transpiler/parser.py     recursive descent → AST (transpiler/ast.py)
   ├── arith   transpiler/arith.py      $((...)) → Python expression
   └── codegen transpiler/codegen.py    AST → readable Python + embedded runtime prelude
```

The generated program is standalone (the runtime helpers are embedded) and can be executed
wherever Python 3.10+ runs.

## Quick start

```bash
# transpile a script and write the Python program to stdout (classic usage)
python trans.py script.sh > script.py

# or write it to a file and execute it
python trans.py script.sh -o script.py
python script.py arg1 arg2

# also works as a module
python -m transpiler script.sh

# syntax-check the generated program
python trans.py script.sh --check

# inspect just the generated statements (without the runtime prelude)
python trans.py script.sh --body-only
```

Example:

```sh
# script.sh
name="Argo"
for i in 1 2 3; do
  echo "$name $i"
done
```

produces (body only):

```python
name = 'Argo'
_status = 0
for i in ['1', '2', '3']:
    _status = _echo(_words((('P', _get('name')), ('q', ' '), ('P', _get('i')),)))
_sys.exit(_status)
```

The full output also includes the runtime prelude; use `--body-only` to see just the
statements.

## Development environment

The project uses [uv](https://docs.astral.sh/uv/) and pins its development dependencies in
`pyproject.toml` + `uv.lock` (pytest, ruff). Python 3.10+ is required.

```bash
# create/update .venv and install dev dependencies
uv sync --dev

# run the test suite inside the managed environment
uv run pytest tests -q

# transpile without activating the environment
uv run python trans.py script.sh -o script.py
```

If you prefer a plain virtualenv, `pip install pytest ruff` works too; no runtime
dependency is needed by the transpiler or by generated programs.

## Supported subset

| Area | Supported |
|---|---|
| Comments / shebang | `#` comments; `#!/bin/dash` ignored (the generated program has its own Python shebang) |
| Quoting | single quotes, double quotes, backslash escapes, line continuation, empty quoted words |
| Parameters | `$name`, `${name}`, `$1`…`$9`, `${10}`, `$#`, `$?`, `$$`, `$@`, `$*`, `${#var}`, `${var:-word}`, `${var:=word}`, `${var:+word}`, `${var:?word}` and the `-`/`=`/`+`/`?` variants; string patterns `${var#pat}`, `${var##pat}`, `${var%pat}`, `${var%%pat}`, `${var/old/new}`, `${var//old/new}` |
| Command substitution | `$(simple command)` and `` `simple command` `` (trailing newlines stripped) |
| Arithmetic | `$((...))` with `+ - * / % ** << >> & \| ^ ~ ! && \|\| == != < <= > >= ?:` and variables; integer division maps to `//` |
| Globbing | unquoted `*`, `?`, `[...]` expanded with `glob`; quoted patterns stay literal |
| Word splitting | unquoted expansions split on the current `IFS` (default space/tab/newline); quoted expansions do not; `IFS=,` also drives `read` and `$*` joining |
| Simple commands | external commands via `subprocess.run`; prefix assignments passed as environment |
| Builtins | `echo` (`-n`, `-e`, `-E`), `cd`, `read` (`-r` accepted), `shift [n]`, `set -e`/`set +e`, `exit`, `true`, `false`, `:`, `pwd`, `export`, `unset` |
| Control flow | `if/elif/else/fi`, `while/do/done`, `until/do/done`, `for NAME in ...; do ...; done`, `for NAME; do ...; done`, `break`, `continue`（暂不支持层数参数） |
| `case` | patterns with `\|` alternation, `*` globs, `*)` default, optional final `;;` |
| Test expressions | `[ ... ]` and `test ...`: `-e -f -d -r -w -x -s -L -h -b -c -p -S -g -u -k -O -G -t -z -n`, `= == != < >`, `-eq -ne -lt -le -gt -ge`, `-a -o ! ( ... )` |
| Lists / operators | `;`, newline, `&&`, `\|\|`, `\|` pipelines |
| Pipelines | external commands plus pure-Python stages `echo`, `grep` (`-i/-v/-c/-n/-q/-F`), `wc` (`-l/-w/-c`), `true`/`false`/`:`; status is the last command's status |
| Redirection | `<`, `>`, `>>`, `1>`, `1>>`, `2>`, `2>>`, `&>`, `&>>`, `2>&1`, `1>&2`, `>&2` on simple commands; input redirection on compound commands (`while read ...; do ...; done < file`) |
| Error reporting | typed `LexError` / `ParseError` / `CodegenError` with filename, line and column; no partial output |

## Deliberate differences from dash

The transpiler is honest about being a subset. These are known differences:

1. **Functions, subshells, background jobs, here-documents, arrays, brace expansion,
   tilde expansion, `[[ ]]`, process substitution, `set -u`, `trap`, `eval`,
   `source`, job control and arithmetic `for ((...))` are not implemented.** They raise a
   `TranspileError` instead of producing broken Python.
2. **Command substitution** supports one simple command (no compound body, assignments or
   redirections inside `$(...)`).
3. **Pipelines** support external commands plus builtin `echo`, `grep` and `wc`; other
   builtins (`cd`, `read`, `exit`, …) inside a pipeline are rejected. Per-stage
   redirections in a pipeline are not supported. `grep`/`wc` are implemented in Python
   (regex syntax is Python's, a close approximation of POSIX BRE) and do not spawn
   external processes.
4. **Output redirection on compound commands** (`if ... fi > log`) is not supported;
   input redirection on compound commands is supported (`while read line; do ...; done < file`).
   Attach other redirections to simple commands instead.
5. **`$10` follows POSIX**: it is `${1}` followed by the literal `0`; use `${10}` for the
   tenth argument.
6. **`$!`** expands to the empty string (no background-job support); `$-` is unsupported.
7. **`IFS`** is supported for the common cases (`IFS=,`, empty `IFS`, unset `IFS`); mixed
   whitespace/non-whitespace `IFS` and empty-field corner cases are approximated.
8. **Mixed quoted/unquoted word expansion** handles the common cases (quoted prefix and
   suffixes, unquoted variable splitting, globbing). A word that concatenates `$@` with
   adjacent text is approximated by joining the arguments with spaces.
9. **`echo` interprets dash-style backslash escapes by default** (`\n`, `\t`, `\c`, octal
   `\0nnn`). This matches dash rather than bash's default.
10. **Status tracking is simplified**: `$?` after a simple or external command is the real
    exit status, but the status of a whole `&&`/`||` list is collapsed to 0/1.
    `set -e`/`set +e` is supported for the common cases: failures in `if`/`while`/`until`
    conditions are ignored, but a failing `&&`/`||` list may exit more eagerly than dash.
11. **`read`** splits using the current `IFS`; `-r` is accepted but backslash processing is
    not modelled. The last named variable receives the remainder of the line (joined by the
    first non-whitespace IFS character).
12. **Internal names** (`_status`, `_echo`, `_get`, …) are reserved; avoid using them as
    shell variable names in transpiled scripts.
13. **`${var:offset:length}` substring expansion is not implemented** (string length
    `${#var}` is).
14. **Python 3.10+** is required to run the generated program.

See [docs/DESIGN.md](docs/DESIGN.md) for the grammar, expansion model and design rationale.

## Tests

```bash
uv sync --dev
uv run pytest tests -q
```

The suite contains unit tests for the lexer, parser and arithmetic translator, golden
body snapshots for the code generator, end-to-end tests that execute the generated Python,
legacy-corpus compatibility tests, CLI tests and differential tests against a real `dash`.

Differential tests are **POSIX/Linux-only**. They are skipped on Windows: a Git-for-Windows
`dash` is found on PATH, but its CRLF/path/pipe behaviour differs from Linux dash and would
produce false failures. On Linux they compare stdout and exit status against
`dash script.sh`.

Latest local run (Windows):

```
333 passed, 29 skipped
```

The 21 skips are exactly the differential tests; on Linux the same suite runs them too.

The archived v1 suite still runs independently:

```bash
uv run pytest legacy/tests -q     # 208 passed
```

## Repository layout

```
trans.py                  CLI entry point
pyproject.toml            project metadata, dev dependencies, pytest/ruff config
uv.lock                   locked development environment
transpiler/
  lexer.py                quote-aware lexer
  tokens.py               token/word-segment data types
  parser.py               recursive-descent parser
  ast.py                  AST dataclasses (with line/column positions)
  arith.py                $((...)) translator
  codegen.py              AST -> Python (table-driven command dispatch)
  runtime.py              runtime prelude embedded in generated programs
  pipeline.py             compile_source(): parse + generate + prelude
  cli.py                  argparse CLI
  errors.py               TranspileError / LexError / ParseError / CodegenError
tests/                    v2 test suite
legacy/                   archived v1 project, tests and README (see legacy/ARCHIVED.md)
docs/DESIGN.md            grammar, semantics and design notes
```

## Migration notes

The old `trans.py`, generated `py/` snapshots, `sh/` differential scripts, `demoRun.sh`,
`test01.sh`, the old README and the old 208-test suite were moved into `legacy/` unchanged.
The old suite still imports the archived `legacy/trans.py` and can be run with
`python -m pytest legacy/tests -q`.

## Roadmap

- `${var:offset:length}` substring expansion
- `set --` / resetting positional parameters
- shell functions with positional parameters and `return`
- compound-command output redirection (`if ... fi > log`)
- here-documents, `[[ ]]`, arrays and brace expansion
- richer pipeline support (all builtins) and `pipefail`
- an `--ast` debugging output and source spans on every AST node (commands already carry
  line/column information)
- GitHub Actions: unit/golden/execution tests on Windows, differential tests on Linux

## Implementation references

The front end borrows a few ideas from existing bash parsers without taking a dependency:
[bashlex](https://github.com/idank/bashlex) keeps source positions on AST nodes and uses a
visitor/tokenizer split; [Parable](https://github.com/ldayton/Parable) validates a complete
bash parser against real bash. v2 adopts positioned AST nodes, slot-based AST dataclasses,
table-driven command dispatch and explicit rejection of unsupported syntax, while keeping
the grammar small and the generated code dependency-free. The differential tests play the
same "compare against real dash" role at a much smaller scale.

## License

MIT — see [LICENSE](LICENSE).

This is a learning project. Always review generated code before executing it, and do not
use it in ways that violate academic-integrity rules.
