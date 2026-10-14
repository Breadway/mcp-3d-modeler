"""Standalone script executed via `blender --background --python blender_render.py -- ...`.

Backend-agnostic preview renderer: imports any mesh file Blender can read
(STL/OBJ/PLY/glTF/GLB/FBX) regardless of which tool produced it, frames it
automatically from the requested angles, and renders one PNG per angle.

STEP files are not handled here -- vanilla Blender has no built-in STEP
importer. The orchestration layer (mcp3d/tools.py) converts STEP to STL via
CadQuery/OCP first and points this script at that intermediate file.

Usage:
    blender --background --python blender_render.py -- \
        <input_path> <output_dir> <width> <height> <angle> [<angle> ...]

Prints one "OK: wrote <path>" line per rendered image, or exits non-zero with
a traceback on stderr on failure.
"""

from __future__ import annotations

import math
import os
import sys
import traceback

import bpy
import mathutils

# Unit direction (from the model's center towards the camera) for each named
# angle. "iso"/"iso2" are classic 3/4 isometric-style views; the rest are
# axis-aligned with a slight tilt so silhouettes read as 3D rather than flat.
ANGLE_DIRECTIONS = {
    "front": (0, -1, 0.35),
    "back": (0, 1, 0.35),
    "left": (-1, 0, 0.35),
    "right": (1, 0, 0.35),
    "top": (0, -0.001, 1),
    "bottom": (0, 0.001, -1),
    "iso": (1, -1, 1),
    "iso2": (-1, -1, 1),
}


def import_mesh(path: str) -> None:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".stl":
        bpy.ops.wm.stl_import(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == ".ply":
        bpy.ops.wm.ply_import(filepath=path)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        try:
            bpy.ops.wm.fbx_import(filepath=path)
        except AttributeError:
            bpy.ops.import_scene.fbx(filepath=path)
    else:
        raise ValueError(f"unsupported input format for rendering: {ext}")


def scene_bounds() -> tuple[mathutils.Vector, float]:
    """World-space (center, radius) bounding sphere of all mesh objects."""
    corners = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            corners.append(obj.matrix_world @ mathutils.Vector(corner))
    if not corners:
        raise ValueError("no mesh objects found after import -- input file appears to be empty")
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    lo = mathutils.Vector((min(xs), min(ys), min(zs)))
    hi = mathutils.Vector((max(xs), max(ys), max(zs)))
    center = (lo + hi) / 2
    radius = max((hi - lo).length / 2, 1e-4)
    return center, radius


def setup_lighting_and_world() -> None:
    world = bpy.data.worlds.new("PreviewWorld")
    world.use_nodes = False
    world.color = (0.85, 0.85, 0.87)
    bpy.context.scene.world = world

    key = bpy.data.objects.new("KeyLight", bpy.data.lights.new("KeyLight", type="SUN"))
    key.data.energy = 3.0
    key.rotation_euler = (math.radians(55), 0, math.radians(35))
    bpy.context.collection.objects.link(key)

    fill = bpy.data.objects.new("FillLight", bpy.data.lights.new("FillLight", type="SUN"))
    fill.data.energy = 1.0
    fill.rotation_euler = (math.radians(110), 0, math.radians(-140))
    bpy.context.collection.objects.link(fill)


def assign_default_material() -> None:
    mat = bpy.data.materials.new("PreviewDefault")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (0.65, 0.68, 0.72, 1.0)
    for obj in bpy.data.objects:
        if obj.type == "MESH" and not obj.data.materials:
            obj.data.materials.append(mat)


def add_camera(center: mathutils.Vector, radius: float) -> bpy.types.Object:
    cam_data = bpy.data.cameras.new("PreviewCamera")
    cam_data.lens = 50
    cam_obj = bpy.data.objects.new("PreviewCamera", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj
    return cam_obj


def point_camera_at(cam_obj: bpy.types.Object, direction: mathutils.Vector, center: mathutils.Vector, distance: float) -> None:
    direction = direction.normalized()
    cam_obj.location = center + direction * distance
    look = (center - cam_obj.location)
    cam_obj.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    if len(argv) < 5:
        print("usage: blender_render.py -- <input> <output_dir> <width> <height> <angle> [...]", file=sys.stderr)
        return 2

    input_path, output_dir, width, height, *angles = argv
    width, height = int(width), int(height)

    unknown = [a for a in angles if a not in ANGLE_DIRECTIONS]
    if unknown:
        print(f"ERROR: unknown angle(s) {unknown}. valid angles: {sorted(ANGLE_DIRECTIONS)}", file=sys.stderr)
        return 1

    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        import_mesh(input_path)
        assign_default_material()
        setup_lighting_and_world()
        center, radius = scene_bounds()

        scene = bpy.context.scene
        scene.render.engine = "BLENDER_EEVEE"
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        scene.render.image_settings.file_format = "PNG"
        scene.render.film_transparent = False

        cam_obj = add_camera(center, radius)
        fov = cam_obj.data.angle if cam_obj.data.angle else math.radians(40)
        distance = (radius / math.tan(fov / 2)) * 1.6

        for angle in angles:
            point_camera_at(cam_obj, mathutils.Vector(ANGLE_DIRECTIONS[angle]), center, distance)
            out_path = os.path.join(output_dir, f"{angle}.png")
            scene.render.filepath = out_path
            bpy.ops.render.render(write_still=True)
            print(f"OK: wrote {out_path}")
    except Exception:
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
