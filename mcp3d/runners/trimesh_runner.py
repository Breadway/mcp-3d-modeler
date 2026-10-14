"""Standalone script executed via `<venv>/bin/python trimesh_runner.py ...`.

Runs arbitrary trimesh script text supplied by the calling LLM: combining
primitives, boolean ops (manifold3d is installed and is trimesh's default
boolean engine, so `a.union(b)` / `trimesh.boolean.union([...])` etc. just
work), mesh repair/cleanup, and procedural generation.

Usage: trimesh_runner.py <script_path> <output_path>

Convention: `trimesh` and `np` (numpy) are in scope. Build the final geometry
and assign it to a module-level variable named `result`, which may be a
trimesh.Trimesh, trimesh.Scene, or a list/tuple of Trimesh objects (these are
combined into a single Scene automatically before export).
"""

from __future__ import annotations

import sys
import traceback

import numpy as np
import trimesh


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: trimesh_runner.py <script_path> <output_path>", file=sys.stderr)
        return 2

    script_path, output_path = sys.argv[1], sys.argv[2]

    with open(script_path, encoding="utf-8") as f:
        code = f.read()

    namespace: dict = {"trimesh": trimesh, "np": np, "numpy": np}
    try:
        exec(compile(code, script_path, "exec"), namespace)
    except Exception:
        print("Script raised an exception while executing:", file=sys.stderr)
        traceback.print_exc()
        return 1

    result = namespace.get("result")
    if result is None:
        print(
            "ERROR: script did not define a variable named `result`. Build your "
            "geometry with the trimesh module and assign the final "
            "Trimesh/Scene (or a list of Trimesh objects) to `result`.",
            file=sys.stderr,
        )
        return 1

    if isinstance(result, (list, tuple)):
        result = trimesh.Scene(list(result))

    try:
        result.export(output_path)
    except Exception:
        print("Export failed:", file=sys.stderr)
        traceback.print_exc()
        return 1

    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
