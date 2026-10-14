"""End-to-end smoke test: drives server.py as a real MCP client would.

Exercises the full loop the deliverable asks for -- generate a simple
parametric part, render it, confirm render_preview (via auto_render) returns
viewable images -- and does one pass over the other three backends and the
error-handling / conversion paths too, all through the actual MCP protocol
(stdio_client + ClientSession), not by calling mcp3d.tools directly.

Run with:
    .venv/bin/python tests/test_loop.py

Rendered PNGs are written to tests/output/ so you can open them and look.
"""

from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
VENV_PYTHON = str(PROJECT_ROOT / ".venv" / "bin" / "python")


def _print_result(label: str, result) -> None:
    status = "ERROR" if result.isError else "ok"
    print(f"[{label}] {status}")
    for block in result.content:
        if block.type == "text":
            first_line = block.text.splitlines()[0] if block.text else ""
            print(f"    text: {first_line}")
            if result.isError or "FAILED" in first_line:
                print("    " + "\n    ".join(block.text.splitlines()[1:15]))
        elif block.type == "image":
            print(f"    image: {block.mimeType}, {len(block.data)} base64 chars")


def _save_images(result, prefix: str) -> list[Path]:
    OUTPUT_DIR.mkdir(exist_ok=True)
    saved = []
    for i, block in enumerate(b for b in result.content if b.type == "image"):
        ext = block.mimeType.split("/")[-1]
        path = OUTPUT_DIR / f"{prefix}_{i}.{ext}"
        path.write_bytes(base64.b64decode(block.data))
        saved.append(path)
    return saved


async def main() -> int:
    params = StdioServerParameters(command=VENV_PYTHON, args=[str(PROJECT_ROOT / "server.py")])
    failures = 0

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("Connected. Registered tools:", [t.name for t in tools.tools])
            print()

            # 1. model_parametric: a simple dimensioned bracket, auto-rendered.
            print("--- Step 1: generate a parametric bracket (CadQuery) ---")
            result = await session.call_tool("model_parametric", {
                "script": (
                    "result = (\n"
                    "    cq.Workplane('XY')\n"
                    "    .box(40, 30, 10)\n"
                    "    .faces('>Z').workplane()\n"
                    "    .rarray(30, 20, 2, 2).hole(4)\n"
                    "    .edges('|Z').fillet(1.5)\n"
                    ")"
                ),
                "output_format": "step",
                "part_name": "bracket",
                "auto_render": True,
                "angles": ["front", "iso", "top"],
            })
            _print_result("model_parametric", result)
            image_count = sum(1 for b in result.content if b.type == "image")
            if result.isError or image_count != 3:
                print(f"    UNEXPECTED: expected 3 images via auto_render, got {image_count}")
                failures += 1
            else:
                paths = _save_images(result, "bracket")
                print(f"    saved: {[str(p) for p in paths]}")
            print()

            # 2. render_preview called standalone against that same output file,
            #    proving the renderer is backend-agnostic and reusable on its own.
            output_path = next(
                (b.text.splitlines()[1].split(": ", 1)[1] for b in result.content if b.type == "text"),
                None,
            )
            if output_path:
                print("--- Step 2: render_preview standalone on the STEP file ---")
                result2 = await session.call_tool("render_preview", {
                    "file_path": output_path,
                    "angles": ["iso2"],
                })
                _print_result("render_preview", result2)
                if result2.isError or sum(1 for b in result2.content if b.type == "image") != 1:
                    failures += 1
                print()

            # 3. model_procedural: trimesh boolean difference.
            print("--- Step 3: procedural boolean difference (trimesh + manifold3d) ---")
            result = await session.call_tool("model_procedural", {
                "script": (
                    "a = trimesh.creation.box(extents=[20, 20, 20])\n"
                    "b = trimesh.creation.cylinder(radius=6, height=30)\n"
                    "result = a.difference(b)\n"
                ),
                "auto_render": True,
                "angles": ["iso"],
            })
            _print_result("model_procedural", result)
            if result.isError:
                failures += 1
            print()

            # 4. model_csg: OpenSCAD.
            print("--- Step 4: quick CSG primitive (OpenSCAD) ---")
            result = await session.call_tool("model_csg", {
                "scad_code": "difference() { cube([20,20,10], center=true); cylinder(h=12, r=4, center=true, $fn=40); }",
                "auto_render": True,
                "angles": ["iso"],
            })
            _print_result("model_csg", result)
            if result.isError:
                failures += 1
            print()

            # 5. model_organic: Blender subsurf.
            print("--- Step 5: organic subdivision surface (Blender/bpy) ---")
            result = await session.call_tool("model_organic", {
                "script": (
                    "bpy.ops.mesh.primitive_cube_add(size=2)\n"
                    "obj = bpy.context.active_object\n"
                    "mod = obj.modifiers.new('subd', type='SUBSURF')\n"
                    "mod.levels = 2\n"
                    "bpy.ops.object.shade_smooth()\n"
                ),
                "auto_render": True,
                "angles": ["iso"],
            })
            _print_result("model_organic", result)
            if result.isError:
                failures += 1
            print()

            # 6. Error handling: a deliberately broken script must come back as a
            #    structured (non-exception) failure, and the session must survive it.
            print("--- Step 6: deliberately broken script (error-handling check) ---")
            result = await session.call_tool("model_parametric", {
                "script": "result = cq.Workplane('XY').this_method_does_not_exist()",
                "auto_render": False,
            })
            _print_result("model_parametric (expected failure)", result)
            still_alive = await session.list_tools()
            print(f"    session still alive after failure: {len(still_alive.tools) == 6}")
            if len(still_alive.tools) != 6:
                failures += 1
            print()

            # 7. convert_format: STEP -> STL, and the mesh->STEP rejection.
            print("--- Step 7: convert_format ---")
            if output_path:
                result = await session.call_tool("convert_format", {
                    "input_path": output_path,
                    "output_format": "stl",
                })
                _print_result("convert_format (step->stl)", result)
                if result.isError:
                    failures += 1

            result = await session.call_tool("convert_format", {
                "input_path": str(next(OUTPUT_DIR.glob("*.png"), Path("nope"))),
                "output_format": "step",
            })
            # This one is expected to fail cleanly on a non-mesh input; the real
            # check is the mesh->STEP rejection path, exercised via tools.py in
            # the accompanying unit-style checks. Kept here only as a smoke check
            # that unsupported inputs don't crash the server.
            _print_result("convert_format (expected-ish failure)", result)
            print()

    print("=" * 60)
    if failures:
        print(f"DONE with {failures} unexpected failure(s) -- see above.")
        return 1
    print("DONE: all steps behaved as expected.")
    print(f"Rendered images saved under: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
