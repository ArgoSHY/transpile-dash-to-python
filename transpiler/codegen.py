"""把语法树转换成独立的 Python 代码。

代码生成器只负责“翻译”，shell 运行时语义尽量放进 runtime.py 的 prelude；
命令节点带行列号，遇到不支持的组合时可以报出准确位置。
"""

from __future__ import annotations

import re
from collections.abc import Callable

from . import arith
from .ast import (
    AndOr,
    Assignment,
    BreakCommand,
    CaseCommand,
    Command,
    Comment,
    ContinueCommand,
    ForCommand,
    IfCommand,
    Pipeline,
    Redirect,
    Script,
    SetCommand,
    SimpleCommand,
    Stmt,
    TestAnd,
    TestBinary,
    TestBool,
    TestExpr,
    TestNot,
    TestOr,
    TestUnary,
    WhileCommand,
)
from .errors import CodegenError
from .parser import parse as parse_source
from .tokens import (
    ArithmeticSegment,
    CommandSubSegment,
    LiteralSegment,
    ParameterSegment,
    Segment,
    Word,
)

_BUILTINS = frozenset(
    {"echo", "cd", "exit", "read", "shift", "true", "false", ":", "pwd", "export", "unset"}
)
_GLOB_CHARS = "*?["
_PATTERN_PARAM_OPS = frozenset({"#", "##", "%", "%%", "/", "//"})
_ALL_REDIRECT_KEYS = frozenset(
    {
        "stdin_path",
        "stdout_path",
        "stdout_append",
        "stderr_path",
        "stderr_append",
        "stderr_to_stdout",
        "stdout_to_stderr",
    }
)
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# 命令节点 -> 生成方法名。用表驱动代替一长串 isinstance，扩展新命令只需注册方法。
_COMMAND_EMITTERS: dict[type[Command], str] = {}


def _emits(node_type: type[Command]) -> Callable[[Callable], Callable]:
    """把 ``_emit_xxx`` 方法注册到命令分发表。"""

    def decorator(method: Callable) -> Callable:
        _COMMAND_EMITTERS[node_type] = method.__name__
        return method

    return decorator


class _Writer:
    """带缩进层级的行写入器。"""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.level = 0

    def line(self, text: str = "", comment: str | None = None) -> int:
        prefix = "    " * self.level
        if comment:
            text = f"{text}  # {comment}" if text else f"# {comment}"
        self.lines.append(prefix + text)
        return len(self.lines) - 1

    def blank(self) -> None:
        self.lines.append("")

    def indent(self) -> None:
        self.level += 1

    def dedent(self) -> None:
        self.level = max(0, self.level - 1)


class CodeGenerator:
    """把 AST 翻译成 Python 语句。"""

    def __init__(self, filename: str = "<script>"):
        self.filename = filename
        self.writer = _Writer()
        # 记录当前嵌套在几层循环里，用于校验 break/continue 的合法性。
        self.loop_depth = 0
        # 复合命令重定向的 with 变量需要唯一名字，避免嵌套时互相覆盖。
        self.redirect_counter = 0
        # 只有脚本里出现 set -e/+e 时才生成 _check_errexit()，避免给普通脚本
        # 增加无意义的运行时调用（也保持旧 golden 输出稳定）。
        self.errexit_checks = False

    # ------------------------------------------------------------------ 对外接口
    def generate(self, script: Script) -> str:
        """生成除 runtime prelude 之外的 Python 语句，末尾补上退出状态。"""
        self.errexit_checks = self._body_uses_errexit(script.body)
        self._emit_body(script.body)
        self.writer.line("_sys.exit(_status)")
        return "\n".join(self.writer.lines) + "\n"

    def _body_uses_errexit(self, body: list[Stmt]) -> bool:
        for node in body:
            if not isinstance(node, AndOr):
                continue
            if self._pipeline_uses_errexit(node.first):
                return True
            if any(self._pipeline_uses_errexit(pipeline) for _, pipeline in node.rest):
                return True
        return False

    def _pipeline_uses_errexit(self, pipeline: Pipeline | None) -> bool:
        if pipeline is None:
            return False
        return any(self._command_uses_errexit(command) for command in pipeline.commands)

    def _command_uses_errexit(self, command: Command) -> bool:
        if isinstance(command, SetCommand):
            return True
        if isinstance(command, IfCommand):
            return any(
                self._body_uses_errexit(branch_body) for _, branch_body in command.branches
            ) or self._body_uses_errexit(command.else_body)
        if isinstance(command, WhileCommand):
            return self._body_uses_errexit(command.body)
        if isinstance(command, ForCommand):
            return self._body_uses_errexit(command.body)
        if isinstance(command, CaseCommand):
            return any(self._body_uses_errexit(item_body) for _, item_body in command.items)
        return False

    def _emit_errexit_check(self) -> None:
        """在可能需要触发 set -e 的语句后生成运行时检查。"""
        if self.errexit_checks:
            self.writer.line("_check_errexit()")

    def _error_for(self, message: str, command: Command) -> CodegenError:
        """构造带命令位置的代码生成错误。"""
        return CodegenError(message, command.line, command.col, self.filename)

    # ------------------------------------------------------------------ 语句
    def _emit_body(self, body: list[Stmt]) -> None:
        for node in body:
            if isinstance(node, Comment):
                self.writer.line(f"# {node.text}" if node.text else "#")
                continue
            first = len(self.writer.lines)
            self._emit_statement(node)
            if node.comment:
                self.writer.lines[first] = self._with_comment(
                    self.writer.lines[first], node.comment
                )

    @staticmethod
    def _with_comment(line: str, comment: str) -> str:
        return f"{line}  # {comment}" if line.strip() else f"# {comment}"

    def _emit_statement(self, node: AndOr) -> None:
        if node.rest:
            expression = self._condition_expr(node)
            self.writer.line(f"_status = 0 if ({expression}) else 1")
            self._emit_errexit_check()
            return
        pipeline = node.first
        if pipeline is None or not pipeline.commands:
            self.writer.line("_status = 0")
            return
        if len(pipeline.commands) == 1:
            command = pipeline.commands[0]
            self._emit_command(command)
            # 复合命令/break/continue 内部各语句已经带了检查；set 自身不检查。
            if isinstance(command, SimpleCommand) and not isinstance(command, SetCommand):
                self._emit_errexit_check()
        else:
            self.writer.line(f"_status = {self._pipeline_expr(pipeline)}")
            self._emit_errexit_check()

    def _emit_command(self, command: Command) -> None:
        emitter_name = _COMMAND_EMITTERS.get(type(command))
        if emitter_name is None:  # pragma: no cover - 防御性分支
            raise CodegenError(
                f"unsupported command AST node {type(command).__name__}",
                command.line,
                command.col,
                self.filename,
            )
        if isinstance(command, (IfCommand, WhileCommand, ForCommand, CaseCommand)):
            if command.redirects:
                self._emit_redirected_compound(command, emitter_name)
                return
        getattr(self, emitter_name)(command)

    def _emit_redirected_compound(self, command: Command, emitter_name: str) -> None:
        """用 ``with open(...)`` 包裹复合命令，块内命令共享同一个 stdin。

        目前只支持输入重定向（如 ``while read line; do ... done < file``）；
        输出重定向需要捕获整个代码块的 stdout，留到后续步骤实现。
        """
        assert isinstance(command, (IfCommand, WhileCommand, ForCommand, CaseCommand))
        redirects = command.redirects
        unsupported = [redirect for redirect in redirects if redirect.op != "<"]
        if unsupported:
            raise self._error_for(
                f"compound command redirection {unsupported[0].op!r} is not supported",
                command,
            )
        if not redirects or redirects[-1].target is None:
            raise self._error_for("compound input redirection needs a file", command)
        path = self._value_expr(redirects[-1].target)
        self.redirect_counter += 1
        variable = f"_dsh_stdin_{self.redirect_counter}"
        self.writer.line(f"with open({path}, 'r', encoding='utf-8') as {variable}:")
        self.writer.indent()
        self.writer.line(f"_stdin_stack.append({variable})")
        self.writer.line("try:")
        self.writer.indent()
        getattr(self, emitter_name)(command)
        self.writer.dedent()
        self.writer.line("finally:")
        self.writer.indent()
        self.writer.line("_stdin_stack.pop()")
        self.writer.dedent()
        self.writer.dedent()

    # ------------------------------------------------------------------ 复合命令
    @_emits(IfCommand)
    def _emit_if(self, command: IfCommand) -> None:
        for index, (condition, body) in enumerate(command.branches):
            keyword = "if" if index == 0 else "elif"
            self.writer.line(f"{keyword} {self._condition_expr(condition)}:")
            self.writer.indent()
            self._emit_body(body)
            if not body:
                self.writer.line("pass")
            self.writer.dedent()
        if command.else_body:
            self.writer.line("else:")
            self.writer.indent()
            self._emit_body(command.else_body)
            if not command.else_body:
                self.writer.line("pass")
            self.writer.dedent()
        else:
            self.writer.line("else:")
            self.writer.indent()
            self.writer.line("_status = 0")
            self.writer.dedent()

    @_emits(WhileCommand)
    def _emit_while(self, command: WhileCommand) -> None:
        condition = self._condition_expr(command.condition) if command.condition else "False"
        if command.until:
            self.writer.line(f"while not ({condition}):")
        else:
            self.writer.line(f"while {condition}:")
        self.writer.indent()
        self.loop_depth += 1
        try:
            self._emit_body(command.body)
            if not command.body:
                self.writer.line("pass")
        finally:
            self.loop_depth -= 1
        self.writer.dedent()

    @_emits(ForCommand)
    def _emit_for(self, command: ForCommand) -> None:
        if command.words is None:
            iterable = "_argv()"
        else:
            iterable = self._argv_expr(command.words)
        self.writer.line(f"for {command.var} in {iterable}:")
        self.writer.indent()
        self.loop_depth += 1
        try:
            self._emit_body(command.body)
            if not command.body:
                self.writer.line("pass")
        finally:
            self.loop_depth -= 1
        self.writer.dedent()

    @_emits(CaseCommand)
    def _emit_case(self, command: CaseCommand) -> None:
        self.writer.line(f"_case_value = {self._value_expr(command.word)}")
        for index, (patterns, body) in enumerate(command.items):
            keyword = "if" if index == 0 else "elif"
            pattern_list = "[" + ", ".join(self._value_expr(pattern) for pattern in patterns) + "]"
            self.writer.line(f"{keyword} _case_match(_case_value, {pattern_list}):")
            self.writer.indent()
            self._emit_body(body)
            if not body:
                self.writer.line("pass")
            self.writer.dedent()
        if command.items:
            self.writer.line("else:")
            self.writer.indent()
            self.writer.line("_status = 0")
            self.writer.dedent()
        else:
            self.writer.line("_status = 0")

    @_emits(BreakCommand)
    def _emit_break(self, command: BreakCommand) -> None:
        if self.loop_depth == 0:
            raise self._error_for("'break' outside a loop", command)
        self.writer.line("break")

    @_emits(ContinueCommand)
    def _emit_continue(self, command: ContinueCommand) -> None:
        if self.loop_depth == 0:
            raise self._error_for("'continue' outside a loop", command)
        self.writer.line("continue")

    @_emits(SetCommand)
    def _emit_set(self, command: SetCommand) -> None:
        self.writer.line(f"_errexit = {command.errexit!r}")
        self.writer.line("_status = 0")

    # ------------------------------------------------------------------ 简单命令
    @_emits(SimpleCommand)
    def _emit_simple(self, command: SimpleCommand) -> None:
        if command.test is not None:
            self.writer.line(f"_status = 0 if {self._test_expr(command.test)} else 1")
            return
        if not command.words:
            self._emit_assignments(command.assignments)
            self.writer.line("_status = 0")
            return
        name = command.words[0].static_text()
        if name == "echo":
            self._emit_echo(command)
        elif name == "cd":
            target = self._value_expr(command.words[1]) if len(command.words) > 1 else '""'
            self.writer.line(f"_status = _cd({target})")
        elif name == "exit":
            arguments = self._argv_expr(command.words[1:])
            self.writer.line(f"_exit({arguments})")
        elif name == "read":
            self._emit_read(command)
        elif name == "shift":
            self.writer.line(f"_status = _shift({self._shift_count_expr(command)})")
        elif name == "export":
            self.writer.line(f"_status = _export({self._argv_expr(command.words[1:])})")
        elif name == "unset":
            self.writer.line(f"_status = _unset({self._argv_expr(command.words[1:])})")
        elif name == "pwd":
            self.writer.line("_status = _pwd()")
        elif name == "true":
            self.writer.line("_status = _true()")
        elif name == "false":
            self.writer.line("_status = _false()")
        elif name == ":":
            self.writer.line("_status = 0")
        elif name is not None and name in _BUILTINS:
            raise self._error_for(f"unsupported builtin {name!r}", command)
        else:
            self._emit_external(command)

    def _emit_assignments(self, assignments: list[Assignment]) -> None:
        for assignment in assignments:
            self.writer.line(f"{assignment.name} = {self._value_expr(assignment.value)}")

    def _shift_count_expr(self, command: SimpleCommand) -> str:
        """把 ``shift [n]`` 的 n 转成表达式；最多允许一个参数。"""
        if len(command.words) > 2:
            raise self._error_for("shift takes at most one argument", command)
        return self._value_expr(command.words[1]) if len(command.words) == 2 else "1"

    def _echo_flags(self, command: SimpleCommand) -> tuple[bool, bool, int]:
        """返回 ``(是否换行, 是否处理反斜杠转义, 消耗的选项个数)``。"""
        newline = True
        escapes = True
        consumed = 0
        for word in command.words[1:]:
            text = word.static_text()
            if text == "-n" and consumed == 0:
                newline = False
                consumed += 1
            elif text == "-e" and consumed <= 1:
                escapes = True
                consumed += 1
            elif text == "-E" and consumed <= 1:
                escapes = False
                consumed += 1
            else:
                break
        return newline, escapes, consumed

    def _emit_echo(self, command: SimpleCommand) -> None:
        newline, escapes, consumed = self._echo_flags(command)
        arguments = self._argv_expr(command.words[1 + consumed :])
        all_kwargs = self._redirect_kwargs(command.redirects, allowed=_ALL_REDIRECT_KEYS)
        kwargs = [
            item for item in all_kwargs if item.split("=", 1)[0] in {"stdout_path", "stdout_append"}
        ]
        if not newline:
            kwargs.append("newline=False")
        if not escapes:
            kwargs.append("escapes=False")
        suffix = ""
        if kwargs:
            suffix = ", " + ", ".join(kwargs)
        self.writer.line(f"_status = _echo({arguments}{suffix})")

    def _read_spec(self, command: SimpleCommand) -> tuple[list[str], str]:
        """解析 read 的变量名和重定向参数，语句和条件两种位置共用。"""
        names: list[str] = []
        for word in command.words[1:]:
            text = word.static_text()
            if text == "-r" and not names:
                # -r 选项接受但忽略：运行时不处理反斜杠续行，语义上差别很小。
                continue
            if text is not None and text.startswith("-") and not names:
                raise self._error_for(f"read: unsupported option {text!r}", command)
            if text is None or not _IDENTIFIER.match(text):
                raise self._error_for("read: variable names must be plain identifiers", command)
            names.append(text)
        kwargs = self._redirect_kwargs(command.redirects, allowed={"stdin_path"})
        suffix = (", " + ", ".join(kwargs)) if kwargs else ""
        return names, suffix

    def _emit_read(self, command: SimpleCommand) -> None:
        names, suffix = self._read_spec(command)
        self.writer.line(f"_status = _read_vars({names!r}{suffix})")

    def _emit_external(self, command: SimpleCommand) -> None:
        arguments = self._argv_expr(command.words)
        kwargs = self._redirect_kwargs(
            command.redirects,
            allowed={
                "stdin_path",
                "stdout_path",
                "stdout_append",
                "stderr_path",
                "stderr_append",
                "stderr_to_stdout",
                "stdout_to_stderr",
            },
        )
        if command.assignments:
            env_pairs = ", ".join(
                f"{assignment.name!r}: {self._value_expr(assignment.value)}"
                for assignment in command.assignments
            )
            kwargs.append(f"env_extra={{{env_pairs}}}")
        suffix = (", " + ", ".join(kwargs)) if kwargs else ""
        self.writer.line(f"_status = _run({arguments}{suffix})")

    # ------------------------------------------------------------------ 重定向
    def _redirect_kwargs(self, redirects: list[Redirect], allowed: set) -> list[str]:
        """把重定向列表转换成运行时函数的 kwargs 字符串列表。"""
        values: dict[str, str] = {}
        for redirect in redirects:
            target = None
            if redirect.target is not None:
                target = self._value_expr(redirect.target)
            if redirect.op == "<":
                values["stdin_path"] = target or '""'
            elif redirect.op in (">", "1>"):
                values["stdout_path"] = target or '""'
                values["stdout_append"] = "False"
            elif redirect.op in (">>", "1>>"):
                values["stdout_path"] = target or '""'
                values["stdout_append"] = "True"
            elif redirect.op == "2>":
                values["stderr_path"] = target or '""'
                values["stderr_append"] = "False"
            elif redirect.op == "2>>":
                values["stderr_path"] = target or '""'
                values["stderr_append"] = "True"
            elif redirect.op in ("&>", "&>>"):
                # stdout/stderr 共用一个句柄：同一个路径打开两次并分别截断会丢流。
                values["stdout_path"] = target or '""'
                values["stdout_append"] = "True" if redirect.op == "&>>" else "False"
                values["stderr_to_stdout"] = "True"
            elif redirect.op == "2>&1":
                values["stderr_to_stdout"] = "True"
            elif redirect.op == "1>&2":
                values["stdout_to_stderr"] = "True"
            else:  # pragma: no cover - 其余情况 parser 已经拒绝
                raise CodegenError(
                    f"unsupported redirection {redirect.op!r}", filename=self.filename
                )
        for key in values:
            if key not in allowed:
                raise CodegenError(
                    f"redirection {key!r} is not supported for this command", filename=self.filename
                )
        return [f"{key}={value}" for key, value in values.items()]

    # ------------------------------------------------------------------ test 表达式
    def _test_expr(self, expression: TestExpr) -> str:
        if isinstance(expression, TestBool):
            return "True" if expression.value else "False"
        if isinstance(expression, TestUnary):
            return f"_test_unary({expression.op!r}, {self._value_expr(expression.operand)})"
        if isinstance(expression, TestBinary):
            return (
                f"_test_binary({expression.op!r}, "
                f"{self._value_expr(expression.left)}, {self._value_expr(expression.right)})"
            )
        if isinstance(expression, TestAnd):
            return f"({self._test_expr(expression.left)} and {self._test_expr(expression.right)})"
        if isinstance(expression, TestOr):
            return f"({self._test_expr(expression.left)} or {self._test_expr(expression.right)})"
        if isinstance(expression, TestNot):
            return f"(not {self._test_expr(expression.expr)})"
        raise CodegenError(
            f"unsupported test expression {type(expression).__name__}", filename=self.filename
        )

    # ------------------------------------------------------------------ 条件表达式
    def _condition_expr(self, node: AndOr) -> str:
        expression = self._pipeline_condition(node.first)
        for operator, pipeline in node.rest:
            right = self._pipeline_condition(pipeline)
            python_op = "and" if operator == "&&" else "or"
            expression = f"({expression} {python_op} {right})"
        return expression

    def _pipeline_condition(self, pipeline: Pipeline | None) -> str:
        if pipeline is None or not pipeline.commands:
            return "True"
        if len(pipeline.commands) == 1:
            return self._command_condition(pipeline.commands[0])
        return f"_ok({self._pipeline_expr(pipeline)})"

    def _command_condition(self, command: Command) -> str:
        if not isinstance(command, SimpleCommand):
            raise self._error_for(
                "compound commands inside '&&' / '||' / conditions are not supported",
                command,
            )
        if command.test is not None:
            return self._test_expr(command.test)
        if not command.words:
            return self._assignment_condition(command.assignments)
        name = command.words[0].static_text()
        if name == "echo":
            newline, escapes, consumed = self._echo_flags(command)
            arguments = self._argv_expr(command.words[1 + consumed :])
            all_kwargs = self._redirect_kwargs(command.redirects, allowed=_ALL_REDIRECT_KEYS)
            kwargs = [
                item
                for item in all_kwargs
                if item.split("=", 1)[0] in {"stdout_path", "stdout_append"}
            ]
            if not newline:
                kwargs.append("newline=False")
            if not escapes:
                kwargs.append("escapes=False")
            suffix = (", " + ", ".join(kwargs)) if kwargs else ""
            return f"_ok(_echo({arguments}{suffix}))"
        if name == "cd":
            target = self._value_expr(command.words[1]) if len(command.words) > 1 else '""'
            return f"_ok(_cd({target}))"
        if name == "export":
            return f"_ok(_export({self._argv_expr(command.words[1:])}))"
        if name == "unset":
            return f"_ok(_unset({self._argv_expr(command.words[1:])}))"
        if name == "true":
            return "True"
        if name == "false":
            return "False"
        if name == ":":
            return "True"
        if name == "pwd":
            return "_ok(_pwd())"
        if name == "shift":
            return f"_ok(_shift({self._shift_count_expr(command)}))"
        if name == "read":
            names, suffix = self._read_spec(command)
            return f"_ok(_read_vars({names!r}{suffix}))"
        if name == "exit":
            raise self._error_for("'exit' in a condition is not supported", command)
        return f"_ok({self._external_call_expr(command)})"

    def _assignment_condition(self, assignments: list[Assignment]) -> str:
        if not assignments:
            return "True"
        parts = [
            f"_set({assignment.name!r}, {self._value_expr(assignment.value)})"
            for assignment in assignments
        ]
        return "(" + " and ".join(parts) + ")"

    def _external_call_expr(self, command: SimpleCommand) -> str:
        arguments = self._argv_expr(command.words)
        kwargs = self._redirect_kwargs(
            command.redirects,
            allowed={
                "stdin_path",
                "stdout_path",
                "stdout_append",
                "stderr_path",
                "stderr_append",
                "stderr_to_stdout",
                "stdout_to_stderr",
            },
        )
        if command.assignments:
            env_pairs = ", ".join(
                f"{assignment.name!r}: {self._value_expr(assignment.value)}"
                for assignment in command.assignments
            )
            kwargs.append(f"env_extra={{{env_pairs}}}")
        suffix = (", " + ", ".join(kwargs)) if kwargs else ""
        return f"_run({arguments}{suffix})"

    def _pipeline_expr(self, pipeline: Pipeline) -> str:
        stages: list[str] = []
        for command in pipeline.commands:
            if not isinstance(command, SimpleCommand) or command.test is not None:
                raise self._error_for(
                    "pipelines currently support only external simple commands", command
                )
            if command.assignments or command.redirects or not command.words:
                raise self._error_for(
                    "pipelines currently support only external simple commands", command
                )
            name = command.words[0].static_text()
            if name == "echo":
                newline, escapes, consumed = self._echo_flags(command)
                arguments = self._argv_expr(command.words[1 + consumed :])
                stages.append(f"('echo', {arguments}, {newline!r}, {escapes!r})")
                continue
            # grep/wc 在这里被截获成纯 Python 阶段，不依赖系统命令。
            if name == "grep":
                stages.append(f"('grep', {self._argv_expr(command.words[1:])})")
                continue
            if name == "wc":
                stages.append(f"('wc', {self._argv_expr(command.words[1:])})")
                continue
            if name in _BUILTINS:
                raise self._error_for(
                    "only echo/grep/wc builtins are supported in pipelines", command
                )
            stages.append(self._argv_expr(command.words))
        return f"_pipeline([{', '.join(stages)}])"

    # ------------------------------------------------------------------ 单词展开
    def _value_expr(self, word: Word | None) -> str:
        if word is None:
            return '""'
        if not word.segments:
            return '""'
        if len(word.segments) == 1 and isinstance(word.segments[0], LiteralSegment):
            return repr(word.segments[0].text)
        return f"_assign({self._parts_tuple(word)})"

    def _argv_expr(self, words: list[Word]) -> str:
        if not words:
            return "[]"
        if all(self._static_word_safe(word) for word in words):
            return "[" + ", ".join(repr(word.segments[0].text) for word in words) + "]"
        return f"_words({', '.join(self._parts_tuple(word) for word in words)})"

    @staticmethod
    def _static_word_safe(word: Word) -> bool:
        if len(word.segments) != 1:
            return False
        segment = word.segments[0]
        if not isinstance(segment, LiteralSegment):
            return False
        if segment.quoted:
            return True
        return not any(char in _GLOB_CHARS for char in segment.text)

    def _parts_tuple(self, word: Word) -> str:
        items: list[str] = []
        for segment in word.segments:
            items.extend(self._segment_parts(segment))
        if not items:
            return "()"
        return "(" + ", ".join(items) + ",)"

    def _segment_parts(self, segment: Segment) -> list[str]:
        if isinstance(segment, LiteralSegment):
            kind = "q" if segment.quoted else "l"
            return [f"({kind!r}, {segment.text!r})"]
        if isinstance(segment, ParameterSegment):
            return self._parameter_parts(segment)
        if isinstance(segment, CommandSubSegment):
            kind = "P" if segment.quoted else "p"
            return [f"({kind!r}, {self._cmdsub_expr(segment)})"]
        if isinstance(segment, ArithmeticSegment):
            kind = "P" if segment.quoted else "p"
            expression = arith.translate(segment.source, self.filename, segment.line, segment.col)
            return [f"({kind!r}, str({expression}))"]
        raise CodegenError(
            f"unsupported word segment {type(segment).__name__}", filename=self.filename
        )

    def _parameter_parts(self, segment: ParameterSegment) -> list[str]:
        name = segment.name
        kind = "P" if segment.quoted else "p"
        # 模式运算优先处理，这样 ${@#x} 这类不支持的特殊参数也会走明确的报错分支。
        if segment.op in _PATTERN_PARAM_OPS:
            return [f"({kind!r}, {self._parameter_pattern_expr(segment)})"]
        if name == "@":
            at_kind = "at_q" if segment.quoted else "at_u"
            return [f"({at_kind!r}, _argv())"]
        if name == "*":
            star_kind = "star_q" if segment.quoted else "star_u"
            return [f"({star_kind!r}, _argv())"]
        if name == "!":
            return [f"({kind!r}, '')"]
        if segment.op is not None:
            return [f"({kind!r}, {self._parameter_default_expr(segment)})"]
        return [f"({kind!r}, {self._parameter_base_expr(name)})"]

    @staticmethod
    def _parameter_base_expr(name: str) -> str:
        if name == "#":
            return "str(_argc())"
        if name == "?":
            return "str(_status)"
        if name == "$":
            return "str(_os.getpid())"
        if name.isdigit():
            return f"_arg({int(name)})"
        return f"_get({name!r})"

    def _parameter_default_expr(self, segment: ParameterSegment) -> str:
        name = segment.name
        operator = segment.op or ""
        default = (
            f"_assign({self._parts_tuple(segment.default)})"
            if segment.default is not None
            else '""'
        )
        base = self._parameter_base_expr(name)
        if operator == ":-":
            return f"(({base}) if ({base}) else ({default}))"
        if operator == "-":
            return f"(({base}) if _is_set({name!r}) else ({default}))"
        if operator == ":+":
            return f"(({default}) if ({base}) else '')"
        if operator == "+":
            return f"(({default}) if _is_set({name!r}) else '')"
        if operator in (":=", "="):
            if not (_IDENTIFIER.match(name)):
                raise CodegenError(f"cannot assign to parameter {name!r}", filename=self.filename)
            only_if_empty = "True" if operator == ":=" else "False"
            return f"_param_assign({name!r}, ({default}), {only_if_empty})"
        if operator in (":?", "?"):
            only_if_empty = "True" if operator == ":?" else "False"
            return f"_param_error({name!r}, ({default}), {only_if_empty})"
        raise CodegenError(f"unsupported parameter operator {operator!r}", filename=self.filename)

    def _parameter_pattern_expr(self, segment: ParameterSegment) -> str:
        """生成 ${var#pat} / ${var%pat} / ${var/old/new} 系列表达式。"""
        name = segment.name
        if name in ("@", "*", "!"):
            raise CodegenError(
                f"pattern expansion is not supported for ${name}",
                filename=self.filename,
            )
        operator = segment.op or ""
        base = self._parameter_base_expr(name)
        pattern = (
            f"_assign({self._parts_tuple(segment.default)})"
            if segment.default is not None
            else '""'
        )
        if operator in ("#", "##", "%", "%%"):
            direction = "prefix" if operator.startswith("#") else "suffix"
            longest = operator in ("##", "%%")
            return f"_param_strip({base}, ({pattern}), {direction!r}, {longest!r})"
        replacement = (
            f"_assign({self._parts_tuple(segment.replacement)})"
            if segment.replacement is not None
            else '""'
        )
        replace_all = operator == "//"
        return f"_param_replace({base}, ({pattern}), ({replacement}), {replace_all!r})"

    def _cmdsub_expr(self, segment: CommandSubSegment) -> str:
        try:
            script = parse_source(segment.source, self.filename)
        except Exception as exc:  # 统一转换成带上下文的代码生成错误
            raise CodegenError(
                f"invalid command substitution $(...): {exc}",
                segment.line,
                segment.col,
                self.filename,
            ) from exc
        if (
            len(script.body) != 1
            or not isinstance(script.body[0], AndOr)
            or script.body[0].rest
            or script.body[0].first is None
            or len(script.body[0].first.commands) != 1
        ):
            raise CodegenError(
                "command substitution supports only a single simple command",
                segment.line,
                segment.col,
                self.filename,
            )
        command = script.body[0].first.commands[0]
        if not isinstance(command, SimpleCommand):
            raise CodegenError(
                "command substitution supports only a single simple command",
                segment.line,
                segment.col,
                self.filename,
            )
        if command.assignments or command.redirects or command.test or not command.words:
            raise CodegenError(
                "command substitution supports only a simple command without redirections",
                segment.line,
                segment.col,
                self.filename,
            )
        name = command.words[0].static_text()
        if name == "echo":
            return f"_cmdsub_echo({self._argv_expr(command.words[1:])})"
        if name in _BUILTINS:
            raise CodegenError(
                f"builtin {name!r} inside command substitution is not supported",
                segment.line,
                segment.col,
                self.filename,
            )
        return f"_cmdsub({self._argv_expr(command.words)})"
