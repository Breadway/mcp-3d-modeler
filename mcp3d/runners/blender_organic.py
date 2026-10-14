"""Standalone script executed via `blender --background --python blender_organic.py -- ...`.

Runs arbitrary bpy script text supplied by the calling LLM against a clean,
empty Blender scene, then exports every mesh object present at the end.
Not imported by the MCP server process -- this always runs as its own
`blender` subprocess, both for isolation and because bpy is only usable
inside the real Blender binary's bundled Python, not a normal venv.

Usage: blender --background --python blender_organic.py -- <script_path> <output_path> <export_format>

Convention: the user script has `bpy` in scope and should build/modify mesh
objects in the scene using normal bpy.ops / bpy.data calls (e.g. add a
primitive, add a Subdivision Surface modifier, use bmesh, sculpt-adjacent
displacement, etc). Every mesh object left in the scene at the end is
exported -- there is no special `result` variable to assign.
"""

from __future__ import annotations

import sys
import traceback

import bpy


def export_scene(output_path: str, fmt: str) -> None:
    bpy.ops.object.select_all(action="SELECT")
    fmt = fmt.lower()
    if fmt == "stl":
        bpy.ops.wm.stl_export(filepath=output_path, export_selected_objects=True)
    elif fmt == "obj":
        bpy.ops.wm.obj_export(filepath=output_path, export_selected_objects=True)
    elif fmt == "ply":
        bpy.ops.wm.ply_export(filepath=output_path, export_selected_objects=True)
    elif fmt == "glb":
        bpy.ops.export_scene.gltf(filepath=output_path, export_format="GLB", use_selection=True)
    elif fmt == "gltf":
        bpy.ops.export_scene.gltf(filepath=output_path, export_format="GLTF_EMBEDDED", use_selection=True)
    elif fmt == "fbx":
        bpy.ops.export_scene.fbx(filepath=output_path, use_selection=True)
    elif fmt == "blend":
        bpy.ops.wm.save_as_mainfile(filepath=output_path)
    else:
        raise ValueError(f"unsupported export format: {fmt}")


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    if len(argv) != 3:
        print("usage: blender_organic.py -- <script_path> <output_path> <export_format>", file=sys.stderr)
        return 2

    script_path, output_path, export_format = argv

    bpy.ops.wm.read_factory_settings(use_empty=True)

    with open(script_path, encoding="utf-8") as f:
        code = f.read()

    try:
        exec(compile(code, script_path, "exec"), {"bpy": bpy})
    except Exception:
        print("Script raised an exception while executing:", file=sys.stderr)
        traceback.print_exc()
        return 1

    mesh_objects = [o for o in bpy.data.objects if o.type == "MESH"]
    if not mesh_objects:
        print(
            "ERROR: no mesh objects exist in the scene after running the script. "
            "Add or build at least one mesh object (e.g. bpy.ops.mesh.primitive_*_add, "
            "or a modifier-based build ending in a MESH object).",
            file=sys.stderr,
        )
        return 1

    try:
        export_scene(output_path, export_format)
    except Exception:
        print("Export failed:", file=sys.stderr)
        traceback.print_exc()
        return 1

    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
