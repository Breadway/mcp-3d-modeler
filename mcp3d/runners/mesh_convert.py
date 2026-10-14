"""Standalone script executed via `<venv>/bin/python mesh_convert.py <in> <out>`.

Generic mesh-format conversion (STL/OBJ/PLY/glTF/GLB/3MF/OFF/...) used by the
convert_format tool, and internally whenever a modeling tool's native export
format doesn't match what the caller asked for. STEP is handled separately
(see cadquery_convert.py) since it's BREP, not a triangle mesh.
"""

from __future__ import annotations

import sys
import traceback

import trimesh

SCENE_ONLY_FORMATS = {"glb", "gltf"}


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: mesh_convert.py <input_path> <output_path>", file=sys.stderr)
        return 2

    input_path, output_path = sys.argv[1], sys.argv[2]
    out_ext = output_path.rsplit(".", 1)[-1].lower()

    try:
        loaded = trimesh.load(input_path)
        if isinstance(loaded, trimesh.Scene) and out_ext not in SCENE_ONLY_FORMATS:
            loaded = loaded.dump(concatenate=True)
        loaded.export(output_path)
    except Exception:
        print("Conversion failed:", file=sys.stderr)
        traceback.print_exc()
        return 1

    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
