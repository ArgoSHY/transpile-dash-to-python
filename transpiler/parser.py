"""支持子集的递归下降解析器。

非正式文法如下（细节见 docs/DESIGN.md）::

    script         := stmt*
    stmt           := and_or (';' | NEWLINE | EOF)
    and_or         := pipeline (('&&' | '||') pipeline)*
    pipeline       := command ('|' command)*
    command        := if_clause | while_clause | until_clause | for_clause
                    | case_clause | simple_command
    simple_command := assignment* (word | redirection)*
    if_clause      := 'if' and_or 'then' stmt* ('elif' and_or 'then' stmt*)*
                      ('else' stmt*)? 'fi'
    while_clause   := 'while' and_or 'do' stmt* 'done'
    until_clause   := 'until' and_or 'do' stmt* 'done'
    for_clause     := 'for' NAME ('in' word*)? (';' | NEWLINE)? 'do' stmt* 'done'
    case_clause    := 'case' word 'in' (pattern ('|' pattern)* ')' stmt* ';;')* 'esac'

不支持的结构统一抛出 :class:`~transpiler.errors.ParseError`，绝不生成半个语法树。
"""

from __future__ import annotations

import re

from .ast import (
    AndOr,
    Assignment,
    CaseCommand,
    Command,
    Comment,
    ForCommand,
    IfCommand,
    Pipeline,
    Redirect,
    Script,
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
from .errors import ParseError
from .lexer import Lexer
from .tokens import LiteralSegment, Token, TokenKind, Word

_ASSIGN_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=")
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_REDIRECT_OPS = frozenset(
    {"<", ">", ">>", "2>", "2>>", "1>", "1>>", "&>", "&>>", "2>&1", "1>&2", "2>&", "1>&"}
)
_RESERVED_WORDS = frozenset(
    {
        "if",
        "then",
        "elif",
        "else",
        "fi",
        "while",
        "until",
        "for",
        "do",
        "done",
        "case",
        "esac",
        "in",
    }
)
_UNARY_TEST_OPS = frozenset(
    {
        "-b",
        "-c",
        "-d",
        "-e",
        "-f",
        "-g",
        "-h",
        "-k",
        "-L",
        "-n",
        "-O",
        "-G",
        "-p",
        "-r",
        "-s",
        "-S",
        "-t",
        "-u",
        "-w",
        "-x",
        "-z",
    }
)
_BINARY_TEST_OPS = frozenset({"==", "=", "!=", "-eq", "-ne", "-lt", "-le", "-gt", "-ge", "<", ">"})


def _literal_text(word: Word | None) -> str | None:
    """取“只有一个纯字面量片段”的单词文本，不关心它是否带引号。"""
    if word is None or len(word.segments) != 1:
        return None
    seg = word.segments[0]
    return seg.text if isinstance(seg, LiteralSegment) else None


class Parser:
    """把 Token 流解析成 :class:`~transpiler.ast.Script`。"""

    def __init__(self, tokens: list[Token], filename: str = "<script>"):
        self.tokens = tokens
        self.filename = filename
        self.index = 0

    # ------------------------------------------------------------------ 基础读取
    def _peek(self, offset: int = 0) -> Token:
        index = self.index + offset
        if index >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[index]

    def _advance(self) -> Token:
        token = self._peek()
        if token.kind != TokenKind.EOF:
            self.index += 1
        return token

    def _error(self, message: str, token: Token | None = None) -> ParseError:
        tok = token or self._peek()
        return ParseError(message, tok.line, tok.col, self.filename)

    def _check_op(self, value: str) -> bool:
        tok = self._peek()
        return tok.kind == TokenKind.OP and tok.value == value

    def _match_op(self, *values: str) -> Token | None:
        tok = self._peek()
        if tok.kind == TokenKind.OP and tok.value in values:
            return self._advance()
        return None

    def _expect_op(self, value: str, context: str) -> Token:
        if not self._check_op(value):
            raise self._error(f"expected {value!r} {context}, got {self._peek().describe()}")
        return self._advance()

    def _check_word(self, text: str) -> bool:
        tok = self._peek()
        return (
            tok.kind == TokenKind.WORD and tok.word is not None and tok.word.static_text() == text
        )

    def _expect_word(self, text: str, context: str) -> Token:
        if not self._check_word(text):
            raise self._error(f"expected {text!r} {context}, got {self._peek().describe()}")
        return self._advance()

    def _expect_word_token(self, context: str) -> Token:
        tok = self._peek()
        if tok.kind != TokenKind.WORD or tok.word is None:
            raise self._error(f"expected a word {context}, got {tok.describe()}")
        return self._advance()

    def _skip_newlines(self) -> None:
        """跳过连续换行。"""
        while self._peek().kind == TokenKind.NEWLINE:
            self._advance()

    def _skip_separators(self) -> None:
        """跳过子句头和子句体之间的换行或分号。"""
        while True:
            tok = self._peek()
            if tok.kind == TokenKind.NEWLINE:
                self._advance()
                continue
            if tok.kind == TokenKind.OP and tok.value == ";":
                self._advance()
                continue
            break

    # ------------------------------------------------------------------ 入口
    def parse(self) -> Script:
        body = self._parse_body(stop_words=frozenset(), stop_ops=frozenset())
        if self._peek().kind != TokenKind.EOF:
            raise self._error(f"unexpected token {self._peek().describe()}")
        return Script(body=body, filename=self.filename)

    def _parse_body(self, stop_words: frozenset[str], stop_ops: frozenset[str]) -> list[Stmt]:
        """解析语句列表，遇到 stop_words/stop_ops 时停下但不消费它。

        这种“带停止集合的 body 解析”让 if/while/for/case 共用同一套语句循环，
        不需要每层再写一遍 while 循环。
        """
        body: list[Stmt] = []
        while True:
            self._skip_newlines()
            while self._match_op(";"):
                self._skip_newlines()
            tok = self._peek()
            if tok.kind == TokenKind.EOF:
                break
            if tok.kind == TokenKind.OP and tok.value in stop_ops:
                break
            if (
                tok.kind == TokenKind.WORD
                and tok.word is not None
                and tok.word.static_text() in stop_words
            ):
                break
            if tok.kind == TokenKind.COMMENT:
                self._advance()
                body.append(Comment(tok.value.strip()))
                continue
            statement = self._parse_and_or()
            # 行尾注释挂在语句上，代码生成时原样带过去。
            if self._peek().kind == TokenKind.COMMENT:
                statement.comment = self._advance().value.strip()
            body.append(statement)
            tok = self._peek()
            if tok.kind in (TokenKind.NEWLINE, TokenKind.EOF):
                continue
            if tok.kind == TokenKind.OP and tok.value in (";", ";;"):
                if tok.value == ";;" and ";;" not in stop_ops:
                    raise self._error("unexpected ';;' outside a case branch")
                if tok.value == ";;":
                    break
                self._advance()
                continue
            if tok.kind == TokenKind.OP and tok.value in stop_ops:
                break
            if (
                tok.kind == TokenKind.WORD
                and tok.word is not None
                and tok.word.static_text() in stop_words
            ):
                break
            raise self._error(f"expected ';' or newline, got {tok.describe()}")
        return body

    # ------------------------------------------------------------------ 列表结构
    def _parse_and_or(self) -> AndOr:
        first = self._parse_pipeline()
        rest: list[tuple[str, Pipeline]] = []
        while True:
            tok = self._peek()
            if tok.kind != TokenKind.OP or tok.value not in ("&&", "||"):
                break
            op = self._advance().value
            self._skip_newlines()
            rest.append((op, self._parse_pipeline()))
        return AndOr(first=first, rest=rest)

    def _parse_pipeline(self) -> Pipeline:
        commands = [self._parse_command()]
        while self._check_op("|"):
            self._advance()
            self._skip_newlines()
            commands.append(self._parse_command())
        return Pipeline(commands=commands)

    # ------------------------------------------------------------------ 命令
    def _parse_command(self) -> Command:
        tok = self._peek()
        if tok.kind == TokenKind.WORD and tok.word is not None:
            text = tok.word.static_text()
            if text == "if":
                return self._parse_if()
            if text == "while":
                return self._parse_while(until=False)
            if text == "until":
                return self._parse_while(until=True)
            if text == "for":
                return self._parse_for()
            if text == "case":
                return self._parse_case()
            if text in _RESERVED_WORDS:
                raise self._error(f"unexpected reserved word {text!r}")
            # 函数定义暂不支持；提前识别并给出明确错误，避免被当成普通命令。
            if (
                self._peek(1).kind == TokenKind.OP
                and self._peek(1).value == "("
                and self._peek(2).kind == TokenKind.OP
                and self._peek(2).value == ")"
            ):
                raise self._error("shell function definitions are not supported", tok)
        return self._parse_simple_command()

    def _parse_simple_command(self) -> SimpleCommand:
        start = self._peek()
        assignments: list[Assignment] = []
        words: list[Word] = []
        redirects: list[Redirect] = []
        while True:
            tok = self._peek()
            if tok.kind == TokenKind.OP and tok.value in _REDIRECT_OPS:
                redirects.append(self._parse_redirect())
                continue
            if tok.kind == TokenKind.WORD and tok.word is not None:
                # 只有命令名之前的 NAME=value 才是赋值，命令名之后的只是普通参数。
                if not words:
                    assignment = self._try_assignment(tok.word)
                    if assignment is not None:
                        self._advance()
                        assignments.append(assignment)
                        continue
                self._advance()
                words.append(tok.word)
                continue
            break
        if not assignments and not words and not redirects:
            raise self._error(f"expected a command, got {self._peek().describe()}")
        test: TestExpr | None = None
        if words:
            name = words[0].static_text()
            if name in ("[", "test"):
                test = self._parse_test(words)
                words = []
        return SimpleCommand(
            assignments=assignments,
            words=words,
            redirects=redirects,
            test=test,
            line=start.line,
            col=start.col,
        )

    def _try_assignment(self, word: Word) -> Assignment | None:
        """判断一个单词是否是 ``NAME=value``，是则拆成赋值节点。"""
        if not word.segments:
            return None
        first = word.segments[0]
        if not isinstance(first, LiteralSegment) or first.quoted:
            return None
        match = _ASSIGN_RE.match(first.text)
        if not match:
            return None
        name = match.group(1)
        rest_text = first.text[match.end() :]
        value_segments: list = []
        if rest_text:
            value_segments.append(LiteralSegment(rest_text, quoted=False, glob=False))
        value_segments.extend(word.segments[1:])
        return Assignment(
            name=name,
            value=Word(tuple(value_segments), line=word.line, col=word.col),
        )

    def _parse_redirect(self) -> Redirect:
        op = self._advance().value
        if op in ("2>&1", "1>&2"):
            return Redirect(op=op, target=None)
        if op in ("2>&", "1>&"):
            raise self._error(f"unsupported file-descriptor duplication {op!r}")
        target = self._expect_word_token(f"after redirection {op!r}").word
        return Redirect(op=op, target=target)

    # ------------------------------------------------------------------ test 表达式
    def _parse_test(self, words: list[Word]) -> TestExpr:
        name = words[0].static_text()
        if name == "[":
            if len(words) < 2 or _literal_text(words[-1]) != "]":
                raise self._error("expected closing ']' for '[' command", words[0])
            content = words[1:-1]
        else:
            content = words[1:]
        return _TestParser(content, self.filename).parse()

    # ------------------------------------------------------------------ 复合命令
    def _parse_if(self) -> IfCommand:
        start = self._expect_word("if", "to start an if statement")
        condition = self._parse_and_or()
        self._skip_separators()
        self._expect_word("then", "after the if condition")
        body = self._parse_body(stop_words=frozenset({"elif", "else", "fi"}), stop_ops=frozenset())
        branches = [(condition, body)]
        while self._check_word("elif"):
            self._advance()
            elif_condition = self._parse_and_or()
            self._skip_separators()
            self._expect_word("then", "after the elif condition")
            elif_body = self._parse_body(
                stop_words=frozenset({"elif", "else", "fi"}), stop_ops=frozenset()
            )
            branches.append((elif_condition, elif_body))
        else_body: list[Stmt] = []
        if self._check_word("else"):
            self._advance()
            self._skip_newlines()
            else_body = self._parse_body(stop_words=frozenset({"fi"}), stop_ops=frozenset())
        self._expect_word("fi", "to close an if statement")
        return IfCommand(branches=branches, else_body=else_body, line=start.line, col=start.col)

    def _parse_while(self, until: bool) -> WhileCommand:
        start = self._expect_word("until" if until else "while", "to start a loop")
        condition = self._parse_and_or()
        self._skip_separators()
        self._expect_word("do", "after the loop condition")
        body = self._parse_body(stop_words=frozenset({"done"}), stop_ops=frozenset())
        self._expect_word("done", "to close a loop")
        return WhileCommand(
            condition=condition,
            body=body,
            until=until,
            line=start.line,
            col=start.col,
        )

    def _parse_for(self) -> ForCommand:
        start = self._expect_word("for", "to start a for loop")
        if self._check_op("("):
            raise self._error("arithmetic for loops are not supported")
        var_token = self._expect_word_token("after 'for'")
        var = _literal_text(var_token.word)
        if var is None or not _NAME_RE.match(var):
            raise self._error(
                f"invalid for-loop variable {var_token.word.static_text()!r}", var_token
            )
        words: list[Word] | None = None
        if self._check_word("in"):
            self._advance()
            words = []
            while True:
                tok = self._peek()
                if tok.kind != TokenKind.WORD or tok.word is None:
                    break
                if tok.word.static_text() in {"do"}:
                    break
                self._advance()
                words.append(tok.word)
        self._skip_separators()
        self._expect_word("do", "after the for-loop header")
        body = self._parse_body(stop_words=frozenset({"done"}), stop_ops=frozenset())
        self._expect_word("done", "to close a for loop")
        return ForCommand(
            var=var,
            words=words,
            body=body,
            line=start.line,
            col=start.col,
        )

    def _parse_case(self) -> CaseCommand:
        start = self._expect_word("case", "to start a case statement")
        word = self._expect_word_token("after 'case'").word
        self._skip_separators()
        self._expect_word("in", "after the case word")
        items: list[tuple[list[Word], list[Stmt]]] = []
        while True:
            self._skip_newlines()
            if self._peek().kind == TokenKind.EOF:
                raise self._error("expected 'esac' to close a case statement")
            if self._check_word("esac"):
                self._advance()
                break
            patterns: list[Word] = [self._expect_word_token("as a case pattern").word]
            while self._match_op("|"):
                patterns.append(self._expect_word_token("as a case pattern").word)
            self._expect_op(")", "after a case pattern")
            body = self._parse_body(stop_words=frozenset({"esac"}), stop_ops=frozenset({";;"}))
            self._match_op(";;")
            items.append((patterns, body))
        return CaseCommand(word=word, items=items, line=start.line, col=start.col)


class _TestParser:
    """解析 ``[ ... ]`` / ``test ...`` 中间的单词列表。"""

    def __init__(self, words: list[Word], filename: str):
        self.words = words
        self.filename = filename
        self.index = 0

    def _peek_text(self) -> str | None:
        if self.index >= len(self.words):
            return None
        return _literal_text(self.words[self.index])

    def _advance(self) -> Word:
        word = self.words[self.index]
        self.index += 1
        return word

    def _error(self, message: str) -> ParseError:
        word = self.words[min(self.index, len(self.words) - 1)] if self.words else Word()
        return ParseError(message, word.line, word.col, self.filename)

    def parse(self) -> TestExpr:
        if not self.words:
            return TestBool(False)
        expression = self._parse_or()
        if self.index != len(self.words):
            raise self._error(f"unexpected test argument {self._peek_text()!r}")
        return expression

    def _parse_or(self) -> TestExpr:
        left = self._parse_and()
        while self._peek_text() == "-o":
            self._advance()
            left = TestOr(left, self._parse_and())
        return left

    def _parse_and(self) -> TestExpr:
        left = self._parse_not()
        while self._peek_text() == "-a":
            self._advance()
            left = TestAnd(left, self._parse_not())
        return left

    def _parse_not(self) -> TestExpr:
        if self._peek_text() == "!":
            self._advance()
            return TestNot(self._parse_not())
        return self._parse_primary()

    def _parse_primary(self) -> TestExpr:
        if self.index >= len(self.words):
            raise self._error("expected a test operand")
        text = self._peek_text()
        if text == "(":
            self._advance()
            expression = self._parse_or()
            if self._peek_text() != ")":
                raise self._error("expected ')' in test expression")
            self._advance()
            return expression
        if text in _UNARY_TEST_OPS:
            op = self._advance()
            operand = self._advance() if self.index < len(self.words) else None
            if operand is None:
                raise self._error(f"missing operand for unary test {op.static_text()!r}")
            return TestUnary(op=op.static_text() or "", operand=operand)
        left = self._advance()
        binary = self._peek_text()
        if binary in _BINARY_TEST_OPS:
            self._advance()
            if self.index >= len(self.words):
                raise self._error(f"missing right operand for test operator {binary!r}")
            right = self._advance()
            return TestBinary(op=binary or "", left=left, right=right)
        # test(1) 里单独一个单词表示“字符串非空”。
        return TestUnary(op="-n", operand=left)


def parse(source: str, filename: str = "<script>") -> Script:
    """词法分析 + 语法分析，返回脚本 AST。"""
    tokens = Lexer(source, filename).tokenize()
    return Parser(tokens, filename).parse()


__all__ = ["Parser", "parse"]
