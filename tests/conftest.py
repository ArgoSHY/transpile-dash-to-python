"""v2 测试套件共用的 fixture。

测试统一使用工作区内的临时目录，而不是 pytest 的 ``tmp_path``：受限的
Windows 沙箱里有时无法在系统临时目录下创建子目录；放在项目内既稳定，
出问题也方便直接查看。
"""

from __future__ import annotations

import itertools
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transpiler import transpile  # noqa: E402


@dataclass
class ShellResult:
    returncode: int
    stdout: str
    stderr: str
    workdir: Path


def write_text_lf(target: Path, content: str) -> None:
    """按 LF 写文件。

    Windows 上 ``Path.write_text`` 默认会把 ``\\n`` 转成 CRLF，而 dash 会把
    行尾的 ``\\r`` 当成普通字符（例如 ``then\\r`` 不再是保留字），导致差分测试
    在 Windows 上莫名其妙地失败。测试脚本和 dash 输入统一用 LF。
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


@pytest.fixture
def scratch(request):
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.nodeid).strip("_")
    path = PROJECT_ROOT / ".pytest-scratch" / name
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def run_shell(scratch):
    counter = itertools.count(1)

    def _run(
        source: str,
        args: Sequence[str] = (),
        stdin: str | None = None,
        files: Mapping[str, str] | None = None,
        dirs: Iterable[str] = (),
        timeout: float = 30,
        env: Mapping[str, str] | None = None,
        program_name: str = "script.py",
    ) -> ShellResult:
        workdir = scratch / f"run{next(counter)}"
        workdir.mkdir(parents=True, exist_ok=True)
        for directory in dirs:
            (workdir / directory).mkdir(parents=True, exist_ok=True)
        for filename, content in (files or {}).items():
            write_text_lf(workdir / filename, content)
        script = workdir / "script.sh"
        write_text_lf(script, source)
        code = transpile(source, filename=str(script))
        program = workdir / program_name
        write_text_lf(program, code)
        child_env = dict(os.environ)
        child_env["PYTHONIOENCODING"] = "utf-8"
        if env:
            child_env.update(env)
        process = subprocess.run(
            [sys.executable, str(program), *args],
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(workdir),
            timeout=timeout,
            env=child_env,
        )
        return ShellResult(process.returncode, process.stdout, process.stderr, workdir)

    return _run


_DASH_PROBE_SCRIPT = """\
x=1
echo $x
if [ $x -eq 1 ]; then echo yes; fi
value=$(echo hi)
echo "[$value]"
read line
echo "read=$line"
"""

_DASH_PROBE_EXPECTED = "1\nyes\n[hi]\nread=hello\n"


def _find_working_dash() -> str | None:
    """找一个真正能按 POSIX 语义执行的 dash。

    只探测 ``exit 0`` 不够：Git for Windows 自带的 dash 能找到、也能退出 0，
    但它的换行/路径行为会让差分结果不可用。这里跑一个包含变量、if、命令替换
    和 read 的小脚本，输出完全一致才认为 dash 可用于差分测试；否则整组跳过，
    留给 Linux CI 跑。
    """
    import shutil as _shutil

    candidates = [
        _shutil.which("dash"),
        "/bin/dash",
        "/usr/bin/dash",
        r"C:\Program Files\Git\usr\bin\dash.exe",
    ]
    for candidate in candidates:
        if not candidate or not Path(candidate).exists():
            continue
        try:
            probe = subprocess.run(
                [candidate, "-c", _DASH_PROBE_SCRIPT],
                input="hello\n",
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.returncode == 0 and probe.stdout == _DASH_PROBE_EXPECTED:
            return candidate
    return None


@pytest.fixture(scope="session")
def dash_path() -> str:
    path = _find_working_dash()
    if path is None:
        pytest.skip("a runnable dash is not available in this environment")
    return path


@pytest.fixture(scope="session")
def dash_env() -> dict:
    env = dict(os.environ)
    path = _find_working_dash()
    if path:
        directory = str(Path(path).parent)
        env["PATH"] = directory + os.pathsep + env.get("PATH", "")
    return env


@pytest.fixture
def run_dash(scratch, dash_path, dash_env):
    counter = itertools.count(1)

    def _run(
        source: str,
        args: Sequence[str] = (),
        stdin: str | None = None,
        files: Mapping[str, str] | None = None,
        timeout: float = 30,
    ) -> ShellResult:
        workdir = scratch / f"dash{next(counter)}"
        workdir.mkdir(parents=True, exist_ok=True)
        for filename, content in (files or {}).items():
            write_text_lf(workdir / filename, content)
        script = workdir / "script.sh"
        write_text_lf(script, source)
        # 用相对路径交给 dash：Windows 上的 Git dash 对绝对路径/盘符处理不稳定。
        process = subprocess.run(
            [dash_path, "script.sh", *args],
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(workdir),
            timeout=timeout,
            env=dash_env,
        )
        return ShellResult(process.returncode, process.stdout, process.stderr, workdir)

    return _run
