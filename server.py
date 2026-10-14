"""MCP server exposing 3D modeling backends (CadQuery, Blender, trimesh,
OpenSCAD) as intent-oriented tools, plus a backend-agnostic renderer so a
calling model can see what it built.

Run with: <venv>/bin/python server.py   (stdio transport)
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.types import Image

from mcp3d import config, tools
from mcp3d.tools import ToolResult

mcp = FastMCP(
    name="3d-modeler",
    instructions=(
        "Tools for generating 3D geometry with whichever backend fits the task, "
        "and for rendering any resulting file to preview images so you can "
        "inspect and refine your work. Pick the modeling tool by the *shape of "
        "the task*, not familiarity: precise mechanical parts -> model_parametric, "
        "organic/sculptural shapes -> model_organic, combining/repairing meshes -> "
        "model_procedural, quick simple CSG -> model_csg. After modeling, call "
        "render_preview (or rely on auto_render) and look at the images before "
        "declaring a task done -- geometry code that runs without error can "
        "still look wrong."
    ),
)


def _result_to_content(result: ToolResult) -> list:
    content: list = []
    if result.success:
        header = f"success\noutput_path: {result.output_path}"
    else:
        header = f"FAILED: {result.error}"
    body = header + ("\n\n" + result.log if result.log else "")
    content.append(body)
    for path in result.image_paths:
        content.append(Image(path=path))
    return content


ANGLES_DOC = (
    "Angles to render, chosen from: front, back, left, right, top, bottom, iso, iso2. "
    "Defaults to ['front', 'iso', 'top'] which is usually enough to judge overall shape."
)


@mcp.tool(
    description=(
        "Generate precise, dimensioned mechanical/engineering geometry with CadQuery: "
        "exact measurements, holes, fillets, chamfers, threads, boolean unions/cuts, "
        "patterns, and multi-part assemblies. Choose this whenever the request involves "
        "specific dimensions, tolerances, or mechanical features (brackets, enclosures, "
        "fasteners, gears, jigs) -- not for freeform/artistic shapes.\n\n"
        "`script` is real CadQuery Python source (the `cq` module is already in scope). "
        "Build geometry with cq.Workplane(...) chains (or cq.Assembly() for multi-part "
        "models) and assign the final object to a variable named `result` -- that is the "
        "only convention required. The script runs in its own subprocess, isolated from "
        "the MCP server and from Blender's process.\n\n"
        "output_format: step (default, preserves exact BREP geometry -- best for CAD "
        "interchange), stl, amf, 3mf, dxf, svg, vrml, brep, bin, or a mesh format "
        "(obj/glb/gltf/ply, produced via an STL intermediate).\n\n"
        "If auto_render is true (default), the part is immediately rendered from the "
        "requested angles and the images are returned alongside the file path, so you "
        "can inspect the result without a separate render_preview call."
    )
)
def model_parametric(
    script: str,
    output_format: str = "step",
    part_name: str = "part",
    auto_render: bool = True,
    angles: list[str] | None = None,
    width: int = 800,
    height: int = 600,
) -> list:
    return _result_to_content(tools.model_parametric(script, output_format, part_name, auto_render, angles, width, height))


@mcp.tool(
    description=(
        "Generate freeform, organic, or sculptural geometry with Blender (bpy): "
        "subdivision surfaces, mesh modifiers (bevel, boolean, array, mirror, solidify, "
        "displace), procedural/sculpt-adjacent mesh building, and materials. Choose this "
        "for shapes that are hard to describe with exact dimensions -- characters, "
        "terrain, abstract forms, stylized objects -- rather than mechanical parts.\n\n"
        "`script` is real bpy Python source executed against a clean, empty Blender "
        "scene (`bpy` is already in scope). Build or modify mesh objects with normal "
        "bpy.ops/bpy.data calls; there is no `result` variable to assign -- every mesh "
        "object left in the scene when the script finishes is exported. Runs inside the "
        "real Blender binary via `blender --background --python`, in its own subprocess "
        "(bpy cannot share a process with CadQuery's OCP bindings).\n\n"
        "output_format: stl (default), obj, ply, glb, gltf, fbx, or blend (a native "
        ".blend scene file, for when you want to keep editing it in Blender directly). "
        "STEP is not available here -- meshes have no BREP topology; use "
        "model_parametric if you need STEP.\n\n"
        "If auto_render is true (default), the result is rendered from the requested "
        "angles and returned as images alongside the file path."
    )
)
def model_organic(
    script: str,
    output_format: str = "stl",
    part_name: str = "part",
    auto_render: bool = True,
    angles: list[str] | None = None,
    width: int = 800,
    height: int = 600,
) -> list:
    return _result_to_content(tools.model_organic(script, output_format, part_name, auto_render, angles, width, height))


@mcp.tool(
    description=(
        "Generate or manipulate geometry procedurally with trimesh: combine primitive "
        "meshes, run boolean operations (union/difference/intersection, backed by the "
        "manifold3d engine), repair broken/non-manifold meshes, resample or decimate, "
        "and do quick procedural generation from math/code rather than sculpting or "
        "parametric CAD. Choose this for programmatic mesh assembly and cleanup tasks, "
        "or as a fast path when you just need a couple of primitives combined.\n\n"
        "`script` is real Python executed with `trimesh` and `np` (numpy) already in "
        "scope. Build the final geometry and assign it to a variable named `result` -- "
        "a trimesh.Trimesh, trimesh.Scene, or a list of Trimesh objects (auto-combined "
        "into a Scene). Runs in its own subprocess.\n\n"
        "output_format: stl (default), obj, ply, glb, gltf, 3mf, off -- trimesh infers "
        "the exporter from this extension directly.\n\n"
        "If auto_render is true (default), the result is rendered from the requested "
        "angles and returned as images alongside the file path."
    )
)
def model_procedural(
    script: str,
    output_format: str = "stl",
    part_name: str = "part",
    auto_render: bool = True,
    angles: list[str] | None = None,
    width: int = 800,
    height: int = 600,
) -> list:
    return _result_to_content(tools.model_procedural(script, output_format, part_name, auto_render, angles, width, height))


@mcp.tool(
    description=(
        "Generate simple parametric shapes with OpenSCAD's declarative CSG language -- "
        "the lightest-weight option for quick primitives, boolean combinations "
        "(union/difference/intersection), and linear/rotational extrusions from a short "
        "script. Choose this over model_parametric when the shape is simple enough that "
        "writing full CadQuery would be overkill (a washer, a simple bracket, a box with "
        "a hole, a quick test primitive).\n\n"
        "`scad_code` is real OpenSCAD source (e.g. `difference() { cube([20,20,10]); "
        "translate([10,10,-1]) cylinder(h=12, r=4); }`). Runs via the `openscad` CLI "
        "binary in its own subprocess.\n\n"
        "output_format: stl (default), off, wrl, amf, 3mf, dxf, svg, csg, png, pdf "
        "(OpenSCAD's native export types), or a mesh format like obj/glb/gltf/ply "
        "(produced via an STL intermediate).\n\n"
        "If auto_render is true (default), the result is rendered from the requested "
        "angles and returned as images alongside the file path."
    )
)
def model_csg(
    scad_code: str,
    output_format: str = "stl",
    part_name: str = "part",
    auto_render: bool = True,
    angles: list[str] | None = None,
    width: int = 800,
    height: int = 600,
) -> list:
    return _result_to_content(tools.model_csg(scad_code, output_format, part_name, auto_render, angles, width, height))


@mcp.tool(
    description=(
        "Render any existing 3D file (STL/OBJ/PLY/glTF/GLB/FBX/STEP) to preview images "
        "from multiple angles, regardless of which tool produced it. Use this to visually "
        "inspect geometry -- after modeling, after a manual edit, or any time you want to "
        "confirm what a file on disk actually looks like before continuing. STEP files "
        "are tessellated to a mesh first automatically.\n\n" + ANGLES_DOC
    )
)
def render_preview(
    file_path: str,
    angles: list[str] | None = None,
    width: int = 800,
    height: int = 600,
) -> list:
    return _result_to_content(tools.render_preview(file_path, angles, width, height))


@mcp.tool(
    description=(
        "Convert a 3D file between common formats (STL, STEP, OBJ, glTF/GLB, PLY, 3MF, "
        "AMF, and more). STEP conversions preserve exact BREP geometry via CadQuery/OCP; "
        "mesh-to-mesh conversions go through trimesh. Converting a mesh format (STL/OBJ/"
        "glTF/...) *to* STEP is not supported and will return an explanatory error -- "
        "meshes are triangle soup with no BREP topology to reconstruct; use "
        "model_parametric if you need real STEP output."
    )
)
def convert_format(input_path: str, output_format: str) -> list:
    return _result_to_content(tools.convert_format(input_path, output_format))


if __name__ == "__main__":
    config.init_session()
    mcp.run(transport="stdio")
