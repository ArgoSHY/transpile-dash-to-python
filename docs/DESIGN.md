# Design notes for transpile-dash-to-python v2

This document records the supported grammar, the expansion model and the contract between
the AST, the code generator and the embedded runtime prelude. It is aimed at future
contributors (and at the author when extending the subset).

## 1. Why a rewrite

v1 was a line-oriented regex replacer: `transpile()` split the script on newlines and tried
to recognise each line with a sequence of `re.search` calls. That approach cannot keep
context (quoting, nesting, redirection scope), produced invalid Python for unsupported
constructs, and represented indentation with an integer counter.

v2 separates the problem into the classic compiler stages:

1. **Lexer** — produces tokens, where every word is a list of segments preserving quoting
   and expansion context.
2. **Parser** — recursive descent into an AST; constructs that are not supported fail with
   a located `ParseError`.
3. **Arithmetic translator** — compiles `$((...))` source into a Python expression.
4. **Code generator** — walks the AST and emits valid Python; indentation is driven by AST
   nesting, never by a counter.
5. **Runtime prelude** — a small, self-contained library embedded into every generated
   program. It implements word expansion, globbing, `echo`, redirection, pipelines, test
   operators, `read`, `cd`, `export`/`unset`, status and parameter operators.

Generated code is intentionally readable enough to audit: statements map one-to-one to
source statements, and helper calls (`_echo`, `_run`, `_words`, `_assign`, `_test_*`) make
shell semantics explicit.

## 2. Grammar

Informal EBNF for the supported subset:

```ebnf
script      := stmt*
stmt        := and_or (";" | NEWLINE | EOF)
and_or      := pipeline (("&&" | "||") pipeline)*
pipeline    := command ("|" command)*
command     := if_clause | while_clause | until_clause | for_clause
             | case_clause | simple_command

if_clause   := "if" and_or "then" stmt*
               ("elif" and_or "then" stmt*)*
               ("else" stmt*)? "fi"
while_clause:= "while" and_or "do" stmt* "done"
until_clause:= "until" and_or "do" stmt* "done"
for_clause  := "for" NAME ("in" word*)? (";" | NEWLINE)? "do" stmt* "done"
case_clause := "case" word "in" case_item* "esac"
case_item   := pattern ("|" pattern)* ")" stmt* (";;")?
pattern     := word

simple_command := assignment* (word | redirect)*
assignment     := NAME "=" word
redirect       := ("<" | ">" | ">>" | "1>" | "1>>" | "2>" | "2>>"
                 | "&>" | "&>>" | "2>&1" | "1>&2") word?
```

Reserved words are only special in command position. Newlines and `;` separate statements;
newlines are also allowed after `&&`, `||` and `|`. Comments (`#` at the start of a token)
are preserved as AST `Comment` nodes or as a trailing comment on the statement.

`test` expressions are parsed from the words inside `[ ... ]` / after `test`:

```ebnf
test_or    := test_and ("-o" test_and)*
test_and   := test_not ("-a" test_not)*
test_not   := "!" test_not | test_primary
test_primary := "(" test_or ")" | unary_op word | word (binary_op word)?
```

## 3. Words and expansion

A word is a tuple of segments:

| Segment | Meaning | Quoted/split/glob |
|---|---|---|
| `LiteralSegment(text, quoted, glob)` | ordinary text, including escaped characters and quoted text | quoted text never splits or globs; unquoted literal text keeps glob characters active |
| `ParameterSegment(name, quoted, op, default)` | `$name`, `$1`, `$#`, `${name:-word}`, … | depends on surrounding quotes |
| `CommandSubSegment(source, quoted)` | `$(...)` / backticks; source parsed recursively at codegen time | quoted → no split/glob |
| `ArithmeticSegment(source, quoted)` | `$((...))` | translated to a Python integer expression |

The runtime performs expansion in two different modes:

* `_assign(parts)` — used for assignment values, `case` values/patterns, here-string-like
  contexts and test operands. It concatenates the parts without splitting or globbing.
* `_expand(parts)` / `_words(*word_parts)` — used for command arguments and loop item
  lists. It builds a character stream annotated with `split` and `glob` flags, splits the
  unquoted parts on IFS whitespace, then pathname-expands each resulting field with
  `glob`. Quoted/escaped characters are marked as non-splitting and non-globbing.

Special handling:

* `$@` quoted/unquoted produces one field per positional argument.
* `$*` joins positional arguments with a space.
* an unquoted empty expansion disappears; a quoted empty expansion (`"$x"`, `""`, `"$@"`
  with no arguments) keeps an empty field.
* `$10` is lexed as `${1}` + literal `0`, matching POSIX.
* the `${...}` operators `:-`, `-`, `:=`, `=`, `:+`, `+`, `:?`, `?` map to runtime helpers
  (`_param_assign`, `_param_error`, `_is_set`);
* the string-pattern operators `${var#pat}`, `${var##pat}`, `${var%pat}`, `${var%%pat}`,
  `${var/old/new}`, `${var//old/new}` map to `_param_strip()` and `_param_replace()`,
  which use glob-style `fnmatch` patterns (quoted glob characters currently still behave as
  patterns — a known approximation).

## 4. Code generation contract

The generated program consists of the Python shebang, the runtime prelude, a marker line
`# --- 以下为生成的程序 ---`, the generated statements and a final `_sys.exit(_status)`.
Command AST nodes carry `line` / `col`, so code-generation errors can point at the exact
command; command emission is table-driven (`_COMMAND_EMITTERS`) instead of an `isinstance`
chain, which mirrors the visitor style used by bashlex.

Important runtime conventions:

| Concept | Representation |
|---|---|
| shell variable read | `_get("name")` (unset reads as `""`) |
| shell variable write | plain assignment `name = 'value'` (module globals) |
| special parameters | `_arg(n)`, `_argc()`, `_argv()`, `_status`, `_os.getpid()` |
| command arguments | `_words(...)` (expansion) or a literal list for static words |
| assignment value | `_assign(...)` |
| echo | `_echo(args, newline=..., escapes=..., stdout_path=..., stdout_append=...)` |
| external command | `_run(argv, stdin_path=..., stdout_path=..., ..., env_extra=...)` |
| pipeline | `_pipeline([stage, ...])`; a stage is an argv list, `('echo', args, newline, escapes)`, `('grep', argv)` or `('wc', argv)`. Stages run sequentially and pass data in memory; external stages use `subprocess.run` |
| test expression | `_test_unary(op, value)` / `_test_binary(op, left, right)` |
| compound input redirection | generated `with open(path) as _dsh_stdin_N:` plus `_stdin_stack.append/pop`; `_run`, `_read_vars`, `_pipeline`, `_cmdsub` default to the stack top |
| status | `_status` is updated after simple commands; `$?` reads it |
| final status | `sys.exit(_status)` |

`if`/`while` conditions reuse the same expression tree: leaves are `_ok(_run(...))` for
external commands, `_echo(...) == 0`-style calls for builtins, or test expressions.
`&&`/`||` map to Python `and`/`or` over boolean leaves, which gives the right short-circuit
behaviour; the final status of such a list is collapsed to 0/1.

Compound-command input redirection is emitted as an actual `with open(...)` wrapper around
the generated block. The wrapper pushes the handle onto `_stdin_stack`; nested compound
redirections push/pop in order. `read` now returns non-zero at EOF, which is what lets
`while read line; do ...; done < file` terminate correctly.

Exit statuses: a simple command/assignment/test/compound statement updates `_status`.
A `while`/`for` loop leaves the last body command's status. An `if` without `else` gets an
implicit `else: _status = 0`, matching the shell's "no branch taken" result.

## 5. Errors

All user-facing diagnostics derive from `TranspileError`:

* `LexError` — unterminated quote/expansion, background job (`&`);
* `ParseError` — missing `then`/`fi`/`do`/`done`/`esac`, function definitions, arithmetic
  `for`, reserved words in the wrong position, malformed test expressions;
* `CodegenError` — constructs the parser accepts but v2 cannot codegen (compound commands
  in `&&`/`||`, builtins other than `echo`/`grep`/`wc` in pipelines, complex command
  substitution, compound-command output redirection, invalid arithmetic).

Each message includes `filename:line:column` and the phase. The CLI exits with status 2
and never prints partial output.

## 6. Testing strategy

1. **Lexer/parser/arith unit tests** assert token/AST structure and error locations.
2. **Golden body snapshots** pin the exact generated statements (runtime prelude stripped
   with `--body-only` / `include_runtime=False`).
3. **End-to-end execution tests** transpile and run the generated Python, checking stdout,
   exit status, produced files and stdin handling.
4. **Legacy-corpus tests** replicate the behaviors the old `sh/` differential harnesses
   checked, without requiring dash on the test machine.
5. **Differential tests** (auto-skipped when dash is unavailable) compare stdout/exit
   status against a real `dash script.sh`.
6. **CLI tests** cover stdout/file output, `--check`, `--body-only`, stdin, error exit
   codes and `python -m transpiler`.

The workspace-local scratch directory (`.pytest-scratch/`) is used instead of `tmp_path`
because restricted Windows sandboxes may not allow creating children under the OS temp
directory.

## 7. Extension guide

To add a new construct:

1. Add tokens/segments in `tokens.py` and scanning in `lexer.py`.
2. Add AST nodes in `ast.py` and parsing in `parser.py` (with a clear `ParseError` for the
   unsupported forms).
3. Add code generation in `codegen.py`; push shell-specific semantics into `runtime.py`.
4. Add tests at the relevant level (unit + golden + execution; differential when possible).
5. Document the construct and any deviation from dash in `README.md`.

Known next steps are listed in the README roadmap (functions, compound-command output
redirection, here-documents, `[[ ]]`, arrays, richer pipelines, `--ast`).

## 8. 参考实现与取舍

* [bashlex](https://github.com/idank/bashlex)：AST 节点带源码位置、tokenizer 与 parser
  分离、用 visitor/kind 组织遍历。v2 借鉴了前两点（命令节点带 `line`/`col`、表驱动
  命令发射器），但没有引入 PLY/yacc 依赖，因为支持的文法很小，手写递归下降更轻。
* [Parable](https://github.com/ldayton/Parable)：一个完整的 bash parser，强调用真实 bash
  做大规模验证。v2 保持“只支持子集”，但把“和真实 dash 对比”固化成可自动跳过的差分
  测试；以后扩大文法时，可以照 Parable 的方式补充语料。
* 共同取舍：解析器只负责结构，shell 语义集中在 `runtime.py`；生成代码只依赖标准库，
  不要求安装任何运行时包。
