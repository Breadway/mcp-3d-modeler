"""Run backend work in a subprocess and capture a structured result.

Every modeling backend (CadQuery, trimesh, Blender, OpenSCAD) is invoked as its
own subprocess. This is deliberate isolation, not just style: bpy and
CadQuery's OCP/OCCT bindings do not tolerate being imported into the same
process, and a crash or infinite loop in LLM-authored script text must not be
able to take down the MCP server itself. Every function here returns a
RunResult instead of raising, so callers can turn failures into a normal
(non-exception) tool result the calling model can read and react to.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field


DEFAULT_TIMEOUT = 120


@dataclass
class RunResult:
    ok: bool
    returncode: int
    stdout: str
    stderr: str
    command: list[str] = field(default_factory=list)
    timed_out: bool = False

    def as_log(self) -> str:
        """Human-readable combined log, safe to hand back to an LLM caller."""
        parts = [f"$ {' '.join(self.command)}", f"exit code: {self.returncode}"]
        if self.timed_out:
            parts.append("(process was killed after exceeding the timeout)")
        if self.stdout.strip():
            parts.append("--- stdout ---\n" + self.stdout.strip())
        if self.stderr.strip():
            parts.append("--- stderr ---\n" + self.stderr.strip())
        return "\n".join(parts)


def run(command: list[str], *, cwd: str | None = None, timeout: int = DEFAULT_TIMEOUT) -> RunResult:
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return RunResult(
            ok=proc.returncode == 0,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            command=command,
        )
    except subprocess.TimeoutExpired as e:
        return RunResult(
            ok=False,
            returncode=-1,
            stdout=(e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""),
            stderr=(e.stderr or b"").decode() if isinstance(e.stderr, bytes) else (e.stderr or ""),
            command=command,
            timed_out=True,
        )
    except FileNotFoundError as e:
        return RunResult(
            ok=False,
            returncode=-1,
            stdout="",
            stderr=f"executable not found: {e}",
            command=command,
        )
