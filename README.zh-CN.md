[English](README.md) | 简体中文

# transpile-dash-to-python v2

一个由文法驱动的小型转译器，把有文档说明的 **dash/POSIX shell 子集** 转换成独立可运行的
Python 3。它用真正的前端替换了原来的正则/逐行改写版本（旧版本保留在 [`legacy/`](legacy/)）：

```
shell 源码
   │
   ├── lexer   transpiler/lexer.py      引号、转义、$var、$(...)、$((...))、操作符
   ├── parser  transpiler/parser.py     递归下降 → AST（transpiler/ast.py）
   ├── arith   transpiler/arith.py      $((...)) → Python 表达式
   └── codegen transpiler/codegen.py    AST → 可读的 Python + 内嵌运行时前导
```

生成的程序是独立可运行的（运行时辅助函数已内嵌），可在任何 Python 3.10+ 环境执行。

## 快速开始

```bash
# 转译脚本并把 Python 程序写到 stdout（经典用法）
python trans.py script.sh > script.py

# 或者写入文件后执行
python trans.py script.sh -o script.py
python script.py arg1 arg2

# 也可以作为模块使用
python -m transpiler script.sh

# 对生成的程序做语法检查
python trans.py script.sh --check

# 只查看生成的语句（不含运行时前导）
python trans.py script.sh --body-only
```

示例：

```sh
# script.sh
name="Argo"
for i in 1 2 3; do
  echo "$name $i"
done
```

生成结果（仅函数体）：

```python
name = 'Argo'
_status = 0
for i in ['1', '2', '3']:
    _status = _echo(_words((('P', _get('name')), ('q', ' '), ('P', _get('i')),)))
_sys.exit(_status)
```

完整输出还包含运行时前导；使用 `--body-only` 可以只看语句部分。

## 开发环境

项目使用 [uv](https://docs.astral.sh/uv/)，开发依赖固定在 `pyproject.toml` + `uv.lock`
（pytest、ruff）。需要 Python 3.10+。`uv.toml` 把 uv 缓存放在项目内（`.uv-cache/`），
因此 `uv run ...` 在无法写入用户级 uv 缓存目录的环境中也能工作。

```bash
# 创建/更新 .venv 并安装开发依赖
uv sync --dev

# 在受管环境中运行测试套件
uv run pytest tests -q

# 不激活环境直接转译
uv run python trans.py script.sh -o script.py
```

如果你更习惯普通 virtualenv，`pip install pytest ruff` 也可以；转译器和生成的程序都
不需要任何运行时依赖。

## 支持的子集

| 领域 | 支持内容 |
|---|---|
| 注释 / shebang | `#` 注释；忽略 `#!/bin/dash`（生成的程序使用自己的 Python shebang） |
| 引号 | 单引号、双引号、反斜杠转义、续行、空引号单词 |
| 参数 | `$name`、`${name}`、`$1`…`$9`、`${10}`、`$#`、`$?`、`$$`、`$@`、`$*`、`${#var}`、`${var:offset}`、`${var:offset:length}`、`${var:-word}`、`${var:=word}`、`${var:+word}`、`${var:?word}` 以及 `-`/`=`/`+`/`?` 变体；字符串模式 `${var#pat}`、`${var##pat}`、`${var%pat}`、`${var%%pat}`、`${var/old/new}`、`${var//old/new}` |
| 命令替换 | `$(简单命令)` 和 `` `简单命令` ``（去掉末尾换行） |
| 算术 | `$((...))`，支持 `+ - * / % ** << >> & \| ^ ~ ! && \|\| == != < <= > >= ?:` 和变量；整数除法映射为 `//` |
| 通配符 | 未加引号的 `*`、`?`、`[...]` 用 `glob` 展开；加引号的模式保持字面量 |
| 单词切分 | 未加引号的展开按当前 `IFS` 切分（默认空格/制表符/换行）；加引号的展开不切分；`IFS=,` 也用于 `read` 和 `$*` 拼接 |
| 简单命令 | 外部命令通过 `subprocess.run` 执行；前缀赋值作为环境变量传入 |
| 内建命令 | `echo`（`-n`、`-e`、`-E`）、`printf`、`cd`、`read`（接受 `-r`）、`shift [n]`、`set -e`/`set +e`、`set -- args...`、`exit`、`true`、`false`、`:`、`pwd`、`export`、`unset` |
| 控制流 | `if/elif/else/fi`、`while/do/done`、`until/do/done`、`for NAME in ...; do ...; done`、`for NAME; do ...; done`、`break`、`continue`（暂不支持层数参数） |
| `case` | 支持 `\|` 交替模式、`*` 通配、`*)` 默认分支、可选的最后一个 `;;` |
| 测试表达式 | `[ ... ]` 和 `test ...`：`-e -f -d -r -w -x -s -L -h -b -c -p -S -g -u -k -O -G -t -z -n`、`= == != < >`、`-eq -ne -lt -le -gt -ge`、`-a -o ! ( ... )` |
| 列表 / 操作符 | `;`、换行、`&&`、`\|\|`、`\|` 管道 |
| 管道 | 外部命令，以及纯 Python 阶段 `echo`、`printf`、`grep`（`-i/-v/-c/-n/-q/-F`）、`wc`（`-l/-w/-c`）、`true`/`false`/`:`；状态取最后一个命令的状态 |
| 重定向 | 简单命令上的 `<`、`>`、`>>`、`1>`、`1>>`、`2>`、`2>>`、`&>`、`&>>`、`2>&1`、`1>&2`、`>&2`；复合命令的输入重定向（`while read ...; do ...; done < file`） |
| 错误报告 | 带文件名、行、列的类型化 `LexError` / `ParseError` / `CodegenError`；不产生部分输出 |

## 与 dash 的有意差异

这个转译器只是一个子集，并对这一点保持诚实。以下是已知差异：

1. **函数、子 shell、后台任务、here-document、数组、花括号展开、波浪号展开、`[[ ]]`、
   进程替换、`set -u`、`trap`、`eval`、`source`、作业控制以及算术 `for ((...))`
   尚未实现。** 它们会抛出 `TranspileError`，而不是生成有问题的 Python。
2. **命令替换**只支持一条简单命令（`$(...)` 内不能有复合命令体、赋值或重定向）。
3. **管道**支持外部命令以及内建 `echo`、`printf`、`grep`、`wc`、`true`/`false`/`:`；
   其他内建命令（`cd`、`read`、`exit` 等）出现在管道中会被拒绝。管道中的逐阶段重定向
   不支持。`printf`、`grep` 和 `wc` 由 Python 实现（grep 的正则语法来自 Python，接近
   POSIX BRE），不会启动外部进程。
4. **复合命令的输出重定向**（`if ... fi > log`）不支持；复合命令的输入重定向是支持的
   （`while read line; do ...; done < file`）。其他重定向请挂在简单命令上。
5. **`$10` 遵循 POSIX**：它等于 `${1}` 后跟字面量 `0`；第十个参数请用 `${10}`。
6. **`$!`** 展开为空字符串（没有后台任务支持）；不支持 `$-`。
7. **`IFS`** 支持常见情况（`IFS=,`、空 `IFS`、未设置 `IFS`）；空白/非空白混合的
   `IFS` 以及空字段边界情况是近似实现。
8. **混合引号/非引号单词展开**覆盖常见情况（带引号的前缀和后缀、未引号变量切分、通配）。
   如果一个单词把 `$@` 和相邻文本拼在一起，会用空格连接参数来近似。
9. **`echo` 默认按 dash 风格解释反斜杠转义**（`\n`、`\t`、`\c`、八进制 `\0nnn`）。
   这与 dash 一致，而不是 bash 的默认行为。
10. **`&&`/`||` 列表保留最后实际执行命令的真实状态**，并按从左到右短路。`set -e`/
    `set +e` 会忽略 `if`/`while`/`until` 条件中的失败，以及 `&&`/`||` 中非最后一条命令
    的失败，覆盖常见 POSIX 场景；作为列表最后一条执行的复合命令失败时仍会触发 `set -e`。
11. **`read`** 按当前 `IFS` 切分；接受 `-r`，但不模拟反斜杠处理。最后一个变量接收该行
    的剩余部分（用第一个非空白 IFS 字符连接）。
12. **内部名称**（`_status`、`_echo`、`_get` 等）是保留的；转译脚本中不要把它们用作
    shell 变量名。
13. **`printf`** 实现了常见的 `%s`、`%b`、`%d`、`%i`、`%u`、`%o`、`%x`、`%X`、
    `%c`、`%f`/`%e`/`%g` 转换以及 flags/宽度/精度；`%q`、`*` 宽度和 `-v` 尚未实现。
14. **需要 Python 3.10+** 才能运行生成的程序。

文法、展开模型和设计取舍见 [docs/DESIGN.md](docs/DESIGN.md)。

## 测试

```bash
uv sync --dev
uv run pytest tests -q
```

测试套件包含 lexer、parser 和算术翻译器的单元测试，代码生成器的 golden 函数体快照，
执行生成 Python 的端到端测试，旧语料兼容测试，CLI 测试，以及针对真实 `dash` 的差分测试。

差分测试**仅支持 POSIX/Linux**。Windows 上会跳过：虽然 PATH 上能找到 Git-for-Windows
的 `dash`，但它的 CRLF/路径/管道行为与 Linux dash 不同，会产生误报失败。在 Linux 上，
它们会把 stdout 和退出状态与 `dash script.sh` 比较。

本地最近一次运行（Windows）：

```
374 passed, 35 skipped
```

这 35 个 skip 正是差分测试；在 Linux 上同一套测试也会运行它们。

归档的 v1 测试套件仍然可以独立运行：

```bash
uv run pytest legacy/tests -q     # 208 passed
```

## 仓库结构

```
trans.py                  命令行入口
pyproject.toml            项目元数据、开发依赖、pytest/ruff 配置
uv.toml                   uv 缓存配置（固定在项目内）
uv.lock                   锁定的开发环境
transpiler/
  lexer.py                感知引号的 lexer
  tokens.py               token/word-segment 数据类型
  parser.py               递归下降 parser
  ast.py                  AST dataclass（带行/列位置）
  arith.py                $((...)) 翻译器
  codegen.py              AST -> Python（表驱动命令分派）
  runtime.py              内嵌到生成程序中的运行时前导
  pipeline.py             compile_source()：解析 + 生成 + 前导
  cli.py                  argparse CLI
  errors.py               TranspileError / LexError / ParseError / CodegenError
tests/                    v2 测试套件
legacy/                   归档的 v1 项目、测试和 README（见 legacy/ARCHIVED.md）
docs/DESIGN.md            文法、语义和设计说明
```

## 迁移说明

旧的 `trans.py`、生成的 `py/` 快照、`sh/` 差分脚本、`demoRun.sh`、`test01.sh`、
旧 README 和旧的 208 测试套件已原样移入 `legacy/`。旧测试套件仍然导入归档的
`legacy/trans.py`，可以用 `python -m pytest legacy/tests -q` 运行。

## 路线图

- 带位置参数和 `return` 的 shell 函数
- 复合命令输出重定向（`if ... fi > log`）
- here-document、`[[ ]]`、数组和花括号展开
- 更完整的管道支持（所有内建命令）和 `pipefail`
- `--ast` 调试输出，以及每个 AST 节点上的源码范围（命令已经带行列信息）
- GitHub Actions：Windows 上运行单元/golden/执行测试，Linux 上运行差分测试

## 实现参考

前端从现有 bash parser 借鉴了一些思路，但不引入运行时依赖：
[bashlex](https://github.com/idank/bashlex) 在 AST 节点上保留源码位置，并采用
visitor/tokenizer 分离；[Parable](https://github.com/ldayton/Parable) 用真实 bash 校验
完整 bash parser。v2 采用带位置的 AST 节点、基于 slot 的 AST dataclass、表驱动命令分派
和显式拒绝不支持的语法，同时保持文法小巧、生成代码无依赖。差分测试在更小的规模上扮演
了同样的“与真实 dash 对比”的角色。

## 许可证

MIT — 见 [LICENSE](LICENSE)。

这是一个学习项目。执行生成的代码前请务必审查，并且不要用于违反学术诚信规定的场景。
