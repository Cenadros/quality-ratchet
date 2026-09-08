from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..errors import CollectorError


def require_tool(name: str, install_hint: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise CollectorError(f"{name} not found: {install_hint}")
    return path


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if check and proc.returncode != 0:
        raise CollectorError(f"{cmd[0]} failed ({proc.returncode}): {proc.stderr.strip()[:500]}")
    return proc


def tool_version(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError:
        return "unknown"
    text = (proc.stdout or proc.stderr).strip()
    return text.splitlines()[0].strip() if text else "unknown"
