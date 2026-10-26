"""嵌入到每个生成程序里的运行时辅助函数。

生成结果必须是自包含的，所以下面整段 prelude 会原样复制到输出文件、放在生成
语句之前。把字段分割、glob、test、重定向、状态这些 shell 语义集中在一个小
运行时里，代码生成器就能保持简单，生成结果也更容易检查。
"""

from __future__ import annotations

PRELUDE = r'''import fnmatch as _fnmatch
import glob as _glob
import os as _os
import re as _re
import subprocess as _subprocess
import sys as _sys

_status = 0
_IFS_WHITESPACE = " \t\n"
# 可变的位置参数列表：$1 对应 _ARGS[0]，shift 直接从这里弹出。
_ARGS = list(_sys.argv[1:])
# 复合命令重定向用的 stdin 栈；块结束时会 pop 掉。
_stdin_stack = []


def _argc():
    return len(_ARGS)


def _argv():
    return list(_ARGS)


def _arg(number):
    index = int(number)
    if index == 0:
        # $0 是脚本名，不参与 shift。
        return _sys.argv[0]
    index -= 1
    if 0 <= index < len(_ARGS):
        return _ARGS[index]
    return ""


def _get(name):
    return globals().get(name, "")


def _set(name, value):
    globals()[name] = str(value)
    return True


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _int(name):
    text = str(name)
    if text.isdigit():
        return _to_int(_arg(int(text)))
    if text == "#":
        return _argc()
    if text == "?":
        return _status
    if text == "$":
        return _os.getpid()
    return _to_int(globals().get(text, 0))


def _is_set(name):
    if name.isdigit():
        return 0 <= int(name) <= len(_ARGS)
    if name in ("#", "?", "$", "@", "*"):
        return True
    return name in globals()


def _shift(count="1"):
    """弹出前 ``count`` 个位置参数；失败时返回 1 且不改动参数。"""
    try:
        value = int(str(count))
    except ValueError:
        _sys.stderr.write(f"shift: {count}: illegal number\n")
        return 1
    if value < 0 or value > len(_ARGS):
        _sys.stderr.write("shift: shift count out of range\n")
        return 1
    del _ARGS[:value]
    return 0


def _assign(parts):
    """在“不分词、不 glob”的上下文里展开单词（赋值右值、case 值等）。"""
    out = []
    for kind, value in parts:
        if kind in ("at_q", "at_u", "star_q", "star_u"):
            out.append(" ".join(str(item) for item in value))
        else:
            out.append(str(value))
    return "".join(out)


def _split_fields(text):
    if text == "":
        return []
    return [field for field in _re.split(r"[ \t\n]+", text) if field != ""]


def _finish_field(field):
    text = "".join(char for char, _active in field)
    if any(active and char in "*?[" for char, active in field):
        pattern = "".join(char if active else _glob.escape(char) for char, active in field)
        matches = sorted(_glob.glob(pattern))
        if matches:
            return matches
    return [text]


def _expand(parts):
    """单词展开：引号保护、字段分割和 pathname glob。

    每个字符都带两个标记：是否参与 IFS 分割、是否保留 glob 含义。先拼成带
    标记的字符流，再按分割点切字段，最后对每个字段做 glob。
    """
    characters = []
    keep_empty = False
    for kind, value in parts:
        if kind in ("q", "P"):
            keep_empty = True
            characters.extend((char, False, False) for char in str(value))
        elif kind == "l":
            characters.extend((char, False, True) for char in str(value))
        elif kind == "p":
            characters.extend((char, True, True) for char in str(value))
        elif kind in ("at_q", "at_u"):
            arguments = [str(item) for item in value]
            if len(parts) == 1:
                result = []
                for argument in arguments:
                    if kind == "at_q":
                        result.append(argument)
                    else:
                        for field in _split_fields(argument):
                            result.extend(_finish_field([(char, True) for char in field]))
                return result
            joined = " ".join(arguments)
            if kind == "at_q":
                keep_empty = True
                characters.extend((char, False, False) for char in joined)
            else:
                characters.extend((char, True, True) for char in joined)
        elif kind in ("star_q", "star_u"):
            joined = " ".join(str(item) for item in value)
            if kind == "star_q":
                keep_empty = True
                characters.extend((char, False, False) for char in joined)
            else:
                characters.extend((char, True, True) for char in joined)
    fields = []
    current = []
    for char, split, globbing in characters:
        if split and char in _IFS_WHITESPACE:
            if current:
                fields.append(current)
                current = []
        else:
            current.append((char, globbing))
    if current:
        fields.append(current)
    if not fields:
        return [""] if keep_empty else []
    result = []
    for field in fields:
        result.extend(_finish_field(field))
    return result


def _words(*word_parts):
    fields = []
    for parts in word_parts:
        fields.extend(_expand(parts))
    return fields


def _write(text, path=None, append=False):
    if path is None:
        _sys.stdout.write(text)
        _sys.stdout.flush()
        return
    with open(path, "a" if append else "w", encoding="utf-8") as handle:
        handle.write(text)


def _escape_echo(text):
    out = []
    index = 0
    mapping = {
        "a": "\a",
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "v": "\v",
        "\\": "\\",
    }
    while index < len(text):
        char = text[index]
        if char != "\\" or index + 1 >= len(text):
            out.append(char)
            index += 1
            continue
        nxt = text[index + 1]
        if nxt == "c":
            break
        if nxt in mapping:
            out.append(mapping[nxt])
            index += 2
            continue
        if nxt in "01234567":
            digits = ""
            index += 1
            while index < len(text) and len(digits) < 3 and text[index] in "01234567":
                digits += text[index]
                index += 1
            out.append(chr(int(digits, 8)))
            continue
        out.append(nxt)
        index += 2
    return "".join(out)


def _echo(args, newline=True, escapes=True, stdout_path=None, stdout_append=False):
    text = " ".join(str(item) for item in args)
    if escapes:
        text = _escape_echo(text)
    if newline:
        text += "\n"
    _write(text, stdout_path, stdout_append)
    return 0


def _cmdsub_echo(args):
    """内建 echo 的命令替换：返回去掉末尾换行的文本。"""
    args = [str(item) for item in args]
    newline = True
    escapes = True
    if args and args[0] == "-n":
        newline = False
        args = args[1:]
    if args and args[0] == "-e":
        escapes = True
        args = args[1:]
    text = " ".join(args)
    if escapes:
        text = _escape_echo(text)
    if newline:
        text += "\n"
    return text.rstrip("\n")


def _cmdsub(argv):
    """简单外部命令的命令替换。"""
    if not argv:
        return ""
    kwargs = {"text": True, "stdout": _subprocess.PIPE}
    if _stdin_stack:
        kwargs["stdin"] = _stdin_stack[-1]
    try:
        result = _subprocess.run(list(argv), **kwargs)
    except OSError:
        return ""
    return result.stdout.rstrip("\n")


def _ok(code):
    return code == 0


def _run(argv, stdin_path=None, stdout_path=None, stdout_append=False,
         stderr_path=None, stderr_append=False, stderr_to_stdout=False,
         stdout_to_stderr=False, env_extra=None):
    if not argv:
        _sys.stderr.write("transpiler: empty command\n")
        return 127
    stdin_handle = stdout_handle = stderr_handle = None
    stdin_owned = False
    try:
        if stdin_path is not None:
            stdin_handle = open(stdin_path, "r", encoding="utf-8")
            stdin_owned = True
        elif _stdin_stack:
            # 复合命令重定向：块内命令默认共享同一个文件句柄，不能在这里关闭。
            stdin_handle = _stdin_stack[-1]
        if stdout_path is not None:
            stdout_handle = open(stdout_path, "a" if stdout_append else "w", encoding="utf-8")
        if stderr_path is not None:
            stderr_handle = open(stderr_path, "a" if stderr_append else "w", encoding="utf-8")
        kwargs = {"stdin": stdin_handle, "stdout": stdout_handle, "stderr": stderr_handle}
        if stderr_to_stdout:
            kwargs["stderr"] = _subprocess.STDOUT
        if stdout_to_stderr:
            kwargs["stdout"] = _sys.stderr
        if env_extra:
            environment = dict(_os.environ)
            environment.update({str(key): str(value) for key, value in env_extra.items()})
            kwargs["env"] = environment
        result = _subprocess.run(list(argv), **kwargs)
        return result.returncode
    except FileNotFoundError:
        _sys.stderr.write(f"{argv[0]}: command not found\n")
        return 127
    except OSError as error:
        _sys.stderr.write(f"{argv[0]}: {error}\n")
        return 126
    finally:
        if stdin_owned and stdin_handle is not None:
            stdin_handle.close()
        for handle in (stdout_handle, stderr_handle):
            if handle is not None:
                handle.close()


def _run_words(fields, **kwargs):
    if not fields:
        _sys.stderr.write("transpiler: empty command\n")
        return 127
    return _run(fields, **kwargs)


def _pipeline_stage_argv(stage):
    """把 pipeline 阶段描述转换成真正的进程参数。

    外部命令阶段本来就是参数列表；内建 echo 阶段则启动一个很小的 Python
    子进程来向管道写数据，这样 ``echo hi | grep h`` 也能正常工作。
    """
    if isinstance(stage, tuple) and stage and stage[0] == "echo":
        _, arguments, newline, escapes = stage
        text = " ".join(str(item) for item in arguments)
        if escapes:
            text = _escape_echo(text)
        if newline:
            text += "\n"
        return [
            _sys.executable,
            "-c",
            "import sys; sys.stdout.write(sys.argv[1])",
            text,
        ]
    return list(stage)


def _pipeline(stages):
    if not stages or any(not stage for stage in stages):
        _sys.stderr.write("transpiler: empty pipeline\n")
        return 127
    processes = []
    previous = None
    try:
        for index, stage in enumerate(stages):
            argv = _pipeline_stage_argv(stage)
            if previous is not None:
                stdin = previous.stdout
            elif _stdin_stack:
                stdin = _stdin_stack[-1]
            else:
                stdin = None
            stdout = _subprocess.PIPE if index < len(stages) - 1 else None
            try:
                process = _subprocess.Popen(argv, stdin=stdin, stdout=stdout)
            except FileNotFoundError:
                _sys.stderr.write(f"{argv[0]}: command not found\n")
                return 127
            except OSError as error:
                _sys.stderr.write(f"{argv[0]}: {error}\n")
                return 126
            if previous is not None and previous.stdout is not None:
                previous.stdout.close()
            processes.append(process)
            previous = process
    finally:
        pass
    return previous.wait()


def _env(pairs):
    return dict(pairs)


def _read_vars(names, stdin_path=None):
    handle = None
    handle_owned = False
    try:
        if stdin_path is not None:
            handle = open(stdin_path, "r", encoding="utf-8")
            handle_owned = True
        elif _stdin_stack:
            handle = _stdin_stack[-1]
        line = handle.readline() if handle is not None else _sys.stdin.readline()
    finally:
        if handle_owned and handle is not None:
            handle.close()
    if line == "":
        # EOF：read 返回非 0，while read 循环因此能正常结束。
        return 1
    if line.endswith("\n"):
        line = line[:-1]
    fields = line.split()
    for index, name in enumerate(names):
        if index == len(names) - 1:
            value = " ".join(fields[index:])
        else:
            value = fields[index] if index < len(fields) else ""
        globals()[name] = value
    return 0


def _cd(target=""):
    if not target:
        target = _os.environ.get("HOME") or _os.environ.get("USERPROFILE") or ""
    if not target:
        _sys.stderr.write("cd: HOME not set\n")
        return 1
    try:
        _os.chdir(target)
        return 0
    except OSError as error:
        _sys.stderr.write(f"cd: {target}: {error.strerror or error}\n")
        return 1


def _pwd():
    _sys.stdout.write(_os.getcwd() + "\n")
    return 0


def _exit(args):
    if not args:
        raise SystemExit(0)
    raise SystemExit(_to_int(args[0]))


def _true():
    return 0


def _false():
    return 1


def _export(args):
    for item in args:
        text = str(item)
        if "=" in text:
            name, value = text.split("=", 1)
            globals()[name] = value
            _os.environ[name] = value
        elif text in globals():
            _os.environ[text] = str(globals()[text])
    return 0


def _unset(args):
    for name in args:
        globals().pop(str(name), None)
        _os.environ.pop(str(name), None)
    return 0


def _num(text):
    try:
        return int(str(text))
    except (TypeError, ValueError):
        _sys.stderr.write(f"transpiler: integer expression expected: {text}\n")
        return 0


def _test_unary(operator, value):
    text = str(value)
    if operator == "-z":
        return len(text) == 0
    if operator == "-n":
        return len(text) > 0
    if operator == "-e":
        return _os.path.exists(text)
    if operator == "-f":
        return _os.path.isfile(text)
    if operator == "-d":
        return _os.path.isdir(text)
    if operator == "-r":
        return _os.access(text, _os.R_OK)
    if operator == "-w":
        return _os.access(text, _os.W_OK)
    if operator == "-x":
        return _os.access(text, _os.X_OK)
    if operator == "-s":
        try:
            return _os.path.getsize(text) > 0
        except OSError:
            return False
    if operator in ("-L", "-h"):
        return _os.path.islink(text)
    if operator == "-t":
        try:
            return _os.isatty(int(text))
        except (ValueError, OSError):
            return False
    try:
        mode = _os.stat(text).st_mode
    except OSError:
        return False
    import stat as _stat
    if operator == "-b":
        return _stat.S_ISBLK(mode)
    if operator == "-c":
        return _stat.S_ISCHR(mode)
    if operator == "-p":
        return _stat.S_ISFIFO(mode)
    if operator == "-S":
        return _stat.S_ISSOCK(mode)
    if operator == "-g":
        return bool(mode & _stat.S_ISGID)
    if operator == "-u":
        return bool(mode & _stat.S_ISUID)
    if operator == "-k":
        return bool(mode & _stat.S_ISVTX)
    if operator == "-O":
        getuid = getattr(_os, "getuid", None)
        return getuid is not None and _os.stat(text).st_uid == getuid()
    if operator == "-G":
        getgid = getattr(_os, "getgid", None)
        return getgid is not None and _os.stat(text).st_gid == getgid()
    return False


def _test_binary(operator, left, right):
    left_text, right_text = str(left), str(right)
    if operator in ("=", "=="):
        return left_text == right_text
    if operator == "!=":
        return left_text != right_text
    if operator == "<":
        return left_text < right_text
    if operator == ">":
        return left_text > right_text
    left_number, right_number = _num(left_text), _num(right_text)
    if operator == "-eq":
        return left_number == right_number
    if operator == "-ne":
        return left_number != right_number
    if operator == "-lt":
        return left_number < right_number
    if operator == "-le":
        return left_number <= right_number
    if operator == "-gt":
        return left_number > right_number
    if operator == "-ge":
        return left_number >= right_number
    return False


def _case_match(value, patterns):
    text = str(value)
    return any(_fnmatch.fnmatchcase(text, str(pattern)) for pattern in patterns)


def _param_assign(name, value, only_if_empty):
    current = globals().get(name, "")
    if only_if_empty and current:
        return str(current)
    globals()[name] = str(value)
    return str(value)


def _param_error(name, message, only_if_empty):
    is_set = name in globals()
    current = globals().get(name, "")
    if not is_set or (only_if_empty and current == ""):
        _sys.stderr.write(f"{name}: {message}\n")
        raise SystemExit(1)
    return str(current)


def _param_strip(value, pattern, direction, longest):
    """${var#pattern} / ${var%pattern} 系列：按 glob 模式裁剪前缀或后缀。"""
    text = str(value)
    pat = str(pattern)
    if pat == "":
        return text
    size = len(text)
    lengths = range(size, -1, -1) if longest else range(0, size + 1)
    if direction == "prefix":
        for length in lengths:
            if _fnmatch.fnmatchcase(text[:length], pat):
                return text[length:]
    else:
        for length in lengths:
            candidate = text[size - length :] if length else ""
            if _fnmatch.fnmatchcase(candidate, pat):
                return text[: size - length] if length else text
    return text


def _param_replace(value, pattern, replacement, replace_all):
    """${var/old/new} / ${var//old/new}：按 glob 模式做替换。"""
    text = str(value)
    pat = str(pattern)
    repl = str(replacement)
    if pat == "":
        return text
    translated = _fnmatch.translate(pat)
    # Python 3.14 把结尾锚点输出成 \z，旧版本是 \Z；两种都去掉，
    # 这样正则可以匹配任意子串，而不要求匹配到字符串末尾。
    if translated.endswith(("\\Z", "\\z")):
        translated = translated[:-2]
    try:
        regex = _re.compile(translated)
    except _re.error:
        return text
    return regex.sub(repl, text, count=0 if replace_all else 1)
'''
