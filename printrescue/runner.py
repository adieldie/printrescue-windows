from __future__ import annotations

import ctypes
import json
import os
import socket
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


@dataclass
class RunResult:
    ok: bool
    code: int
    stdout: str
    stderr: str
    command: str


def run(
    command: list[str] | str,
    *,
    timeout: int = 90,
    shell: bool = False,
    input_text: str | None = None,
) -> RunResult:
    rendered = command if isinstance(command, str) else subprocess.list2cmdline(command)
    try:
        cp = subprocess.run(
            command,
            shell=shell,
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        return RunResult(
            cp.returncode == 0,
            cp.returncode,
            cp.stdout.strip(),
            cp.stderr.strip(),
            rendered,
        )
    except subprocess.TimeoutExpired:
        return RunResult(False, 124, "", "Tempo limite excedido.", rendered)
    except OSError as exc:
        return RunResult(False, 1, "", str(exc), rendered)


def ps_quote(value: str) -> str:
    return value.replace("'", "''")


def powershell(script: str, *, timeout: int = 120) -> RunResult:
    return run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        timeout=timeout,
    )


def powershell_tempfile(
    script: str,
    *,
    timeout: int = 120,
    input_text: str | None = None,
) -> RunResult:
    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".ps1",
            encoding="utf-8-sig",
            delete=False,
        ) as fh:
            fh.write(script)
            path = Path(fh.name)
        return run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(path),
            ],
            timeout=timeout,
            input_text=input_text,
        )
    finally:
        if path:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def is_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def elevate_current_process() -> bool:
    if os.name != "nt" or is_admin():
        return False
    import sys

    executable = sys.executable
    if getattr(sys, "frozen", False):
        params = " ".join(f'"{arg}"' for arg in sys.argv[1:])
    else:
        params = " ".join(f'"{arg}"' for arg in [str(Path(sys.argv[0]).resolve()), *sys.argv[1:]])
    code = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", executable, params, None, 1
    )
    return code > 32


def hostname() -> str:
    return os.environ.get("COMPUTERNAME", socket.gethostname()).upper()


def tcp_test(host: str, port: int, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "Conexão estabelecida."
    except OSError as exc:
        return False, str(exc)


def resolve_ipv4(host: str) -> str:
    try:
        return socket.gethostbyname(host)
    except OSError:
        return ""


def parse_json_output(result: RunResult, fallback: Any = None) -> Any:
    if not result.ok or not result.stdout:
        return fallback
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return fallback
