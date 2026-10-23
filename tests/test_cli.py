"""``trans.py`` / ``python -m transpiler`` 命令行接口测试。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRAN_PY = PROJECT_ROOT / "trans.py"
PYTHON = sys.executable


def run_cli(args, stdin=None, cwd=None):
    return subprocess.run(
        [PYTHON, str(TRAN_PY), *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(cwd or PROJECT_ROOT),
        timeout=60,
    )


def test_cli_prints_program_to_stdout(scratch):
    script = scratch / "demo.sh"
    script.write_text("echo hello\n", encoding="utf-8")
    result = run_cli([str(script)])
    assert result.returncode == 0
    assert result.stdout.startswith("#!/usr/bin/env python3\n")
    assert "_status = _echo(['hello'])" in result.stdout
    compile(result.stdout, "<generated>", "exec")


def test_cli_body_only(scratch):
    script = scratch / "demo.sh"
    script.write_text("echo hello\n", encoding="utf-8")
    result = run_cli([str(script), "--body-only"])
    assert result.returncode == 0
    assert result.stdout == "_status = _echo(['hello'])\n_sys.exit(_status)\n"


def test_cli_output_file_and_execution(scratch):
    script = scratch / "demo.sh"
    script.write_text("echo from-file\n", encoding="utf-8")
    output = scratch / "demo.py"
    result = run_cli([str(script), "-o", str(output)])
    assert result.returncode == 0
    assert output.exists()
    executed = subprocess.run(
        [PYTHON, str(output)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(scratch),
        timeout=30,
    )
    assert executed.stdout == "from-file\n"


def test_cli_check_flag_accepts_valid_output(scratch):
    script = scratch / "demo.sh"
    script.write_text("for i in 1 2; do echo $i; done\n", encoding="utf-8")
    result = run_cli([str(script), "--check"])
    assert result.returncode == 0
    assert result.stdout


def test_cli_reads_stdin(scratch):
    result = run_cli([], stdin="echo from-stdin\n")
    assert result.returncode == 0
    assert "_echo(['from-stdin'])" in result.stdout


def test_cli_missing_file(scratch):
    result = run_cli([str(scratch / "missing.sh")])
    assert result.returncode == 2
    assert "trans.py:" in result.stderr


def test_cli_reports_parse_error(scratch):
    script = scratch / "bad.sh"
    script.write_text("if true; then echo x\n", encoding="utf-8")
    result = run_cli([str(script)])
    assert result.returncode == 2
    assert "parse error" in result.stderr
    assert "bad.sh:2" in result.stderr


def test_cli_reports_lex_error(scratch):
    script = scratch / "bad.sh"
    script.write_text("sleep 1 &\n", encoding="utf-8")
    result = run_cli([str(script)])
    assert result.returncode == 2
    assert "lex error" in result.stderr


def test_cli_version():
    result = run_cli(["--version"])
    assert result.returncode == 0
    assert "2.0.0" in result.stdout


def test_module_entry_point(scratch):
    script = scratch / "demo.sh"
    script.write_text("echo module\n", encoding="utf-8")
    result = subprocess.run(
        [PYTHON, "-m", "transpiler", str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(PROJECT_ROOT),
        timeout=60,
    )
    assert result.returncode == 0
    assert "_echo(['module'])" in result.stdout
