"""支持子集的 AST 节点定义。

命令节点都带 ``line`` / ``col`` 位置信息，代码生成阶段报错时可以给出准确位置，
思路参考 bashlex 给 AST 节点附带源码位置的实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .tokens import Word


# --------------------------------------------------------------------- 单词与重定向
@dataclass(frozen=True, slots=True)
class Assignment:
    name: str
    value: Word


@dataclass(frozen=True, slots=True)
class Redirect:
    op: str
    target: Word | None = None


# --------------------------------------------------------------------- test 表达式
class TestExpr:
    """``[ ... ]`` / ``test ...`` 表达式节点的基类。"""

    # 这些类名以 Test 开头，设置 __test__ 防止 pytest 误把它们当测试类收集。
    __test__ = False
    __slots__ = ()


@dataclass(frozen=True, slots=True)
class TestUnary(TestExpr):
    op: str
    operand: Word


@dataclass(frozen=True, slots=True)
class TestBinary(TestExpr):
    op: str
    left: Word
    right: Word


@dataclass(frozen=True, slots=True)
class TestAnd(TestExpr):
    left: TestExpr
    right: TestExpr


@dataclass(frozen=True, slots=True)
class TestOr(TestExpr):
    left: TestExpr
    right: TestExpr


@dataclass(frozen=True, slots=True)
class TestNot(TestExpr):
    expr: TestExpr


@dataclass(frozen=True, slots=True)
class TestBool(TestExpr):
    value: bool


# --------------------------------------------------------------------- 命令节点
class Command:
    """所有命令节点的基类。"""

    __slots__ = ()


@dataclass
class SimpleCommand(Command):
    assignments: list[Assignment] = field(default_factory=list)
    words: list[Word] = field(default_factory=list)
    redirects: list[Redirect] = field(default_factory=list)
    test: TestExpr | None = None
    line: int = 1
    col: int = 1


@dataclass
class IfCommand(Command):
    branches: list[tuple[AndOr, list[Stmt]]] = field(default_factory=list)
    else_body: list[Stmt] = field(default_factory=list)
    redirects: list[Redirect] = field(default_factory=list)
    line: int = 1
    col: int = 1


@dataclass
class WhileCommand(Command):
    condition: AndOr | None = None
    body: list[Stmt] = field(default_factory=list)
    until: bool = False
    redirects: list[Redirect] = field(default_factory=list)
    line: int = 1
    col: int = 1


@dataclass
class ForCommand(Command):
    var: str = ""
    words: list[Word] | None = None
    body: list[Stmt] = field(default_factory=list)
    redirects: list[Redirect] = field(default_factory=list)
    line: int = 1
    col: int = 1


@dataclass
class CaseCommand(Command):
    word: Word | None = None
    items: list[tuple[list[Word], list[Stmt]]] = field(default_factory=list)
    redirects: list[Redirect] = field(default_factory=list)
    line: int = 1
    col: int = 1


@dataclass
class BreakCommand(Command):
    """循环内 ``break``；由代码生成器校验必须位于循环中。"""

    line: int = 1
    col: int = 1


@dataclass
class ContinueCommand(Command):
    """循环内 ``continue``；由代码生成器校验必须位于循环中。"""

    line: int = 1
    col: int = 1


@dataclass
class SetCommand(Command):
    """``set -e`` / ``set +e``，以及 ``set -- args...`` 重置位置参数。"""

    errexit: bool | None = None
    args: list[Word] | None = None
    line: int = 1
    col: int = 1


# --------------------------------------------------------------------- 程序结构
@dataclass(slots=True)
class Pipeline:
    commands: list[Command] = field(default_factory=list)


@dataclass(slots=True)
class AndOr:
    first: Pipeline | None = None
    rest: list[tuple[str, Pipeline]] = field(default_factory=list)
    comment: str | None = None


@dataclass(frozen=True, slots=True)
class Comment:
    text: str


@dataclass(slots=True)
class Script:
    body: list[AndOr | Comment] = field(default_factory=list)
    filename: str = "<script>"


Stmt = AndOr | Comment

__all__ = [
    "Assignment",
    "Redirect",
    "TestExpr",
    "TestUnary",
    "TestBinary",
    "TestAnd",
    "TestOr",
    "TestNot",
    "TestBool",
    "Command",
    "SimpleCommand",
    "IfCommand",
    "WhileCommand",
    "ForCommand",
    "CaseCommand",
    "BreakCommand",
    "ContinueCommand",
    "SetCommand",
    "Pipeline",
    "AndOr",
    "Comment",
    "Script",
    "Stmt",
]
