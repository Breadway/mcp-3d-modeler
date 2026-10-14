"""Shared paths, binaries, and per-session scratch directory management."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNNERS_DIR = PROJECT_ROOT / "mcp3d" / "runners"
SCRATCH_ROOT = Path(os.environ.get("MCP3D_SCRATCH_ROOT", PROJECT_ROOT / "scratch"))

# The Python interpreter that has cadquery/trimesh/manifold3d installed (this
# venv). Runner scripts for those backends are executed with this interpreter,
# in their own subprocess, never imported into the server's own process.
VENV_PYTHON = os.environ.get("MCP3D_VENV_PYTHON", str(Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python"))

BLENDER_BIN = os.environ.get("MCP3D_BLENDER_BIN") or shutil.which("blender") or "blender"
OPENSCAD_BIN = os.environ.get("MCP3D_OPENSCAD_BIN") or shutil.which("openscad") or "openscad"

# One subdirectory per server process lifetime ("session"), so concurrent runs
# of the server (or repeated restarts during development) don't collide or
# accumulate forever in a single flat directory.
_SESSION_ID = uuid.uuid4().hex[:8]
SESSION_DIR = SCRATCH_ROOT / f"session-{_SESSION_ID}"


def init_session() -> Path:
    """Create (or recreate) this process's scratch directory."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return SESSION_DIR


def session_path(name: str) -> Path:
    """Return a path inside the current session's scratch directory."""
    return SESSION_DIR / name


def new_id() -> str:
    return uuid.uuid4().hex[:8]
