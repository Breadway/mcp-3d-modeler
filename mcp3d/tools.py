"""Orchestration layer: each function here backs one MCP tool.

Every function returns a ToolResult (never raises for an expected failure
mode -- subprocess crashes, bad user scripts, unsupported formats). server.py
turns ToolResult into MCP content blocks (text + inline images).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mcp3d import config
from mcp3d.subprocess_utils import run

DEFAULT_ANGLES = ["front", "iso", "top"]
VALID_ANGLES = {"front", "back", "left", "right", "top", "bottom", "iso", "iso2"}

# Formats cq.exporters.export / cq.Assembly.save can write directly from a
# BREP shape, without going through a mesh-conversion side trip.
CQ_NATIVE_FORMATS = {"step", "stl", "amf", "svg", "dxf", "vrml", "3mf", "brep", "bin"}
CQ_EXPORT_TYPE = {
    "step": "STEP", "stl": "STL", "amf": "AMF", "svg": "SVG", "dxf": "DXF",
    "vrml": "VRML", "3mf": "3MF", "brep": "BREP", "bin": "BIN",
}

# Formats OpenSCAD's CLI can write directly via `-o out.<fmt>`.
OPENSCAD_NATIVE_FORMATS = {"stl", "off", "wrl", "amf", "3mf", "dxf", "svg", "csg", "png", "pdf"}

# Formats blender_organic.py's exporter dispatch supports directly.
BLENDER_NATIVE_FORMATS = {"stl", "obj", "ply", "glb", "gltf", "fbx", "blend"}

# Formats blender_render.py can import directly (it wraps Blender's own
# importers). Anything else gets bridged through trimesh -> STL first.
BLENDER_IMPORTABLE_FORMATS = {"stl", "obj", "ply", "glb", "gltf", "fbx"}

RUNNERS = config.RUNNERS_DIR


@dataclass
class ToolResult:
    success: bool
    output_path: str | None = None
    log: str = ""
    error: str | None = None
    image_paths: list[str] = field(default_factory=list)


def _ext(fmt_or_path: str) -> str:
    return fmt_or_path.rsplit(".", 1)[-1].lower()


def _normalize_angles(angles: list[str] | None) -> tuple[list[str] | None, str | None]:
    angles = angles or DEFAULT_ANGLES
    bad = [a for a in angles if a not in VALID_ANGLES]
    if bad:
        return None, f"unknown angle(s) {bad}; valid angles are {sorted(VALID_ANGLES)}"
    return angles, None


def _render(input_path: Path, angles: list[str], width: int, height: int) -> ToolResult:
    """Shared rendering path used by render_preview and every model_* tool's auto_render."""
    angles, err = _normalize_angles(angles)
    if err:
        return ToolResult(success=False, error=err)

    ext = _ext(str(input_path))
    render_input = input_path

    if ext in ("step", "stp"):
        bridged = input_path.with_suffix(".render-bridge.stl")
        conv = run([
            config.VENV_PYTHON, str(RUNNERS / "cadquery_convert.py"),
            str(input_path), str(bridged), "STL",
        ])
        if not conv.ok:
            return ToolResult(success=False, error="failed to tessellate STEP for rendering", log=conv.as_log())
        render_input = bridged
    elif ext not in BLENDER_IMPORTABLE_FORMATS:
        bridged = input_path.with_suffix(".render-bridge.stl")
        conv = run([config.VENV_PYTHON, str(RUNNERS / "mesh_convert.py"), str(input_path), str(bridged)])
        if not conv.ok:
            return ToolResult(success=False, error=f"could not bridge .{ext} to a renderable format", log=conv.as_log())
        render_input = bridged

    out_dir = input_path.parent / f"{input_path.stem}-renders"
    out_dir.mkdir(parents=True, exist_ok=True)

    result = run([
        config.BLENDER_BIN, "--background", "--python", str(RUNNERS / "blender_render.py"),
        "--", str(render_input), str(out_dir), str(width), str(height), *angles,
    ], timeout=180)

    image_paths = [str(out_dir / f"{a}.png") for a in angles]
    missing = [p for p in image_paths if not Path(p).exists()]
    if not result.ok or missing:
        return ToolResult(success=False, error="render failed", log=result.as_log())

    return ToolResult(success=True, log=result.as_log(), image_paths=image_paths)


def _maybe_auto_render(path: Path, auto_render: bool, angles: list[str] | None, width: int, height: int) -> tuple[list[str], str]:
    if not auto_render:
        return [], ""
    render_result = _render(path, angles or DEFAULT_ANGLES, width, height)
    if render_result.success:
        return render_result.image_paths, ""
    return [], f"\n[auto_render failed]\n{render_result.error}\n{render_result.log}"


def model_parametric(
    script: str,
    output_format: str = "step",
    part_name: str = "part",
    auto_render: bool = True,
    angles: list[str] | None = None,
    width: int = 800,
    height: int = 600,
) -> ToolResult:
    session = config.init_session()
    uid = config.new_id()
    fmt = output_format.lower()
    if fmt not in CQ_EXPORT_TYPE and fmt not in ("obj", "glb", "gltf", "ply", "off"):
        return ToolResult(success=False, error=(
            f"unsupported output_format '{output_format}' for model_parametric. "
            f"Supported: {sorted(CQ_EXPORT_TYPE) + ['obj', 'glb', 'gltf', 'ply', 'off']}"
        ))

    script_path = session / f"{part_name}_{uid}.cq.py"
    script_path.write_text(script, encoding="utf-8")

    if fmt in CQ_NATIVE_FORMATS:
        final_path = session / f"{part_name}_{uid}.{fmt}"
        result = run([config.VENV_PYTHON, str(RUNNERS / "cadquery_runner.py"), str(script_path), str(final_path), CQ_EXPORT_TYPE[fmt]])
        log = result.as_log()
    else:
        stl_path = session / f"{part_name}_{uid}.stl"
        final_path = session / f"{part_name}_{uid}.{fmt}"
        result = run([config.VENV_PYTHON, str(RUNNERS / "cadquery_runner.py"), str(script_path), str(stl_path), "STL"])
        log = result.as_log()
        if result.ok:
            conv = run([config.VENV_PYTHON, str(RUNNERS / "mesh_convert.py"), str(stl_path), str(final_path)])
            log += "\n" + conv.as_log()
            result = conv

    if not result.ok:
        return ToolResult(success=False, error="model_parametric failed", log=log)

    image_paths, render_note = _maybe_auto_render(final_path, auto_render, angles, width, height)
    return ToolResult(success=True, output_path=str(final_path), log=log + render_note, image_paths=image_paths)


def model_organic(
    script: str,
    output_format: str = "stl",
    part_name: str = "part",
    auto_render: bool = True,
    angles: list[str] | None = None,
    width: int = 800,
    height: int = 600,
) -> ToolResult:
    session = config.init_session()
    uid = config.new_id()
    fmt = output_format.lower()

    if fmt == "step":
        return ToolResult(success=False, error=(
            "model_organic produces meshes (triangles), which have no BREP topology to "
            "write as STEP. Use model_parametric if you need a STEP output."
        ))

    script_path = session / f"{part_name}_{uid}.bpy.py"
    script_path.write_text(script, encoding="utf-8")

    if fmt in BLENDER_NATIVE_FORMATS:
        final_path = session / f"{part_name}_{uid}.{fmt}"
        result = run([config.BLENDER_BIN, "--background", "--python", str(RUNNERS / "blender_organic.py"),
                      "--", str(script_path), str(final_path), fmt], timeout=180)
        log = result.as_log()
    else:
        stl_path = session / f"{part_name}_{uid}.stl"
        final_path = session / f"{part_name}_{uid}.{fmt}"
        result = run([config.BLENDER_BIN, "--background", "--python", str(RUNNERS / "blender_organic.py"),
                      "--", str(script_path), str(stl_path), "stl"], timeout=180)
        log = result.as_log()
        if result.ok:
            conv = run([config.VENV_PYTHON, str(RUNNERS / "mesh_convert.py"), str(stl_path), str(final_path)])
            log += "\n" + conv.as_log()
            result = conv

    if not result.ok:
        return ToolResult(success=False, error="model_organic failed", log=log)

    image_paths, render_note = _maybe_auto_render(final_path, auto_render, angles, width, height)
    return ToolResult(success=True, output_path=str(final_path), log=log + render_note, image_paths=image_paths)


def model_procedural(
    script: str,
    output_format: str = "stl",
    part_name: str = "part",
    auto_render: bool = True,
    angles: list[str] | None = None,
    width: int = 800,
    height: int = 600,
) -> ToolResult:
    session = config.init_session()
    uid = config.new_id()
    fmt = output_format.lower()

    script_path = session / f"{part_name}_{uid}.trimesh.py"
    script_path.write_text(script, encoding="utf-8")
    final_path = session / f"{part_name}_{uid}.{fmt}"

    result = run([config.VENV_PYTHON, str(RUNNERS / "trimesh_runner.py"), str(script_path), str(final_path)])
    if not result.ok:
        return ToolResult(success=False, error="model_procedural failed", log=result.as_log())

    image_paths, render_note = _maybe_auto_render(final_path, auto_render, angles, width, height)
    return ToolResult(success=True, output_path=str(final_path), log=result.as_log() + render_note, image_paths=image_paths)


def model_csg(
    scad_code: str,
    output_format: str = "stl",
    part_name: str = "part",
    auto_render: bool = True,
    angles: list[str] | None = None,
    width: int = 800,
    height: int = 600,
) -> ToolResult:
    session = config.init_session()
    uid = config.new_id()
    fmt = output_format.lower()

    scad_path = session / f"{part_name}_{uid}.scad"
    scad_path.write_text(scad_code, encoding="utf-8")

    if fmt in OPENSCAD_NATIVE_FORMATS:
        final_path = session / f"{part_name}_{uid}.{fmt}"
        result = run([config.OPENSCAD_BIN, "-o", str(final_path), str(scad_path)], timeout=180)
        log = result.as_log()
    else:
        stl_path = session / f"{part_name}_{uid}.stl"
        final_path = session / f"{part_name}_{uid}.{fmt}"
        result = run([config.OPENSCAD_BIN, "-o", str(stl_path), str(scad_path)], timeout=180)
        log = result.as_log()
        if result.ok:
            conv = run([config.VENV_PYTHON, str(RUNNERS / "mesh_convert.py"), str(stl_path), str(final_path)])
            log += "\n" + conv.as_log()
            result = conv

    if not result.ok:
        return ToolResult(success=False, error="model_csg failed", log=log)

    image_paths, render_note = _maybe_auto_render(final_path, auto_render, angles, width, height)
    return ToolResult(success=True, output_path=str(final_path), log=log + render_note, image_paths=image_paths)


def render_preview(
    file_path: str,
    angles: list[str] | None = None,
    width: int = 800,
    height: int = 600,
) -> ToolResult:
    path = Path(file_path)
    if not path.exists():
        return ToolResult(success=False, error=f"file not found: {file_path}")
    angles = angles or DEFAULT_ANGLES
    return _render(path, angles, width, height)


def convert_format(input_path: str, output_format: str) -> ToolResult:
    in_path = Path(input_path)
    if not in_path.exists():
        return ToolResult(success=False, error=f"file not found: {input_path}")

    session = config.init_session()
    uid = config.new_id()
    in_ext = _ext(str(in_path))
    out_ext = output_format.lower()
    final_path = session / f"converted_{uid}.{out_ext}"

    if in_ext in ("step", "stp"):
        if out_ext in CQ_EXPORT_TYPE:
            result = run([config.VENV_PYTHON, str(RUNNERS / "cadquery_convert.py"), str(in_path), str(final_path), CQ_EXPORT_TYPE[out_ext]])
            log = result.as_log()
        else:
            stl_path = session / f"converted_{uid}.stl"
            result = run([config.VENV_PYTHON, str(RUNNERS / "cadquery_convert.py"), str(in_path), str(stl_path), "STL"])
            log = result.as_log()
            if result.ok:
                conv = run([config.VENV_PYTHON, str(RUNNERS / "mesh_convert.py"), str(stl_path), str(final_path)])
                log += "\n" + conv.as_log()
                result = conv
        if not result.ok:
            return ToolResult(success=False, error="convert_format failed", log=log)
        return ToolResult(success=True, output_path=str(final_path), log=log)

    if out_ext in ("step", "stp"):
        return ToolResult(success=False, error=(
            f"cannot convert a mesh format (.{in_ext}) to STEP: STEP stores real BREP "
            "topology (faces/edges/surfaces), which a triangle mesh does not have and "
            "cannot be reliably reconstructed into. If you need a STEP output, author "
            "the geometry directly with model_parametric instead."
        ))

    result = run([config.VENV_PYTHON, str(RUNNERS / "mesh_convert.py"), str(in_path), str(final_path)])
    if not result.ok:
        return ToolResult(success=False, error="convert_format failed", log=result.as_log())
    return ToolResult(success=True, output_path=str(final_path), log=result.as_log())
