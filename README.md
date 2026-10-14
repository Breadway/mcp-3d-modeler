# mcp-3d-modeler

An MCP server that gives an LLM four different 3D modeling backends as
intent-oriented tools, plus a backend-agnostic renderer, so it can generate
geometry, look at what it built, and iterate.

| Tool | Backend | Best for |
|---|---|---|
| `model_parametric` | CadQuery | precise dimensions, holes, fillets, booleans, assemblies |
| `model_organic` | Blender (`bpy`, via `blender --background --python`) | freeform/sculptural shapes, subdivision surfaces, modifiers |
| `model_procedural` | trimesh (+ manifold3d) | combining primitives, boolean ops, mesh repair |
| `model_csg` | OpenSCAD | quick declarative CSG when CadQuery is overkill |
| `render_preview` | Blender (headless renderer) | multi-angle preview images of any mesh/STEP file |
| `convert_format` | trimesh / CadQuery-OCP | STL/STEP/OBJ/glTF/PLY/3MF/... conversion |

Every modeling tool takes a script/code string (real CadQuery/bpy/trimesh/
OpenSCAD source, not a fixed parameter schema), runs it in its own
subprocess, and - by default (`auto_render=True`) - renders the result and
returns the images inline in the same tool call, so there's no required
second round-trip.

## Architecture

```
server.py            MCP server (FastMCP, stdio transport), tool descriptions
mcp3d/
  config.py          scratch dir / binary path management
  subprocess_utils.py subprocess runner, returns a structured RunResult (never raises)
  tools.py            orchestration: one function per tool, dispatches to runners
  runners/
    cadquery_runner.py    exec'd by the venv's python - model_parametric
    trimesh_runner.py     exec'd by the venv's python - model_procedural
    mesh_convert.py       exec'd by the venv's python - mesh<->mesh conversion
    cadquery_convert.py   exec'd by the venv's python - STEP source conversion
    blender_organic.py    exec'd *by Blender itself* - model_organic
    blender_render.py     exec'd *by Blender itself* - render_preview
scratch/              per-session working directory (gitignored)
tests/test_loop.py     full end-to-end test over the real MCP protocol
```

Every backend runs as its own subprocess:

- CadQuery and trimesh scripts run under this project's own venv (`.venv/bin/python`),
  each invocation a fresh subprocess - never imported into the server's process.
- Blender scripts run inside the actual `blender` binary via `blender --background
  --python <script> -- <args>`. This is not the `bpy` pip package; it's the real
  Blender executable running its own bundled interpreter. That sidesteps the
  well-known conflict between `bpy` and CadQuery's OCP/OCCT bindings entirely -
  they never share a process, or even a Python interpreter.
- OpenSCAD runs via its CLI binary directly (`openscad -o out.stl in.scad`).

Every runner script prints `OK: wrote <path>` on success or a real Python
traceback on stderr on failure, and every orchestration function in
`tools.py` returns a `ToolResult` dataclass (`success`, `output_path`, `log`,
`error`, `image_paths`) instead of raising. `server.py` turns that into MCP
content blocks - text plus inline `Image` blocks - with `isError` staying
`False` even on a failed script, so a bad LLM-authored script comes back as
readable, structured feedback the model can act on, and never kills the MCP
connection.

## Setup

Requires: a `blender` binary, an `openscad` binary, and a Python environment
with the packages below. Tested on Arch Linux with Blender 5.2 and OpenSCAD
2021.01 from the `extra` repo; adjust package names for other distros.

```bash
# system dependencies (Arch)
sudo pacman -S blender openscad

# recommended: also install python-cattrs system-wide (see gotcha below)
sudo pacman -S python-cattrs

# project + Python deps
cd mcp-3d-modeler
uv venv .venv
uv sync
```

`pyproject.toml` pins:

```toml
dependencies = [
    "mcp>=1.29.0,<2.0.0",
    "cadquery>=2.5.2",
    "trimesh>=4.0.0",
    "manifold3d>=3.0.0",
    "numpy",
    "pillow",
]
```

If `blender` or `openscad` aren't on `PATH`, point at them explicitly:

```bash
export MCP3D_BLENDER_BIN=/path/to/blender
export MCP3D_OPENSCAD_BIN=/path/to/openscad
```

### Running the server

```bash
.venv/bin/python server.py
```

It speaks MCP over stdio. Point any MCP client at that command, e.g. for
Claude Code:

```bash
claude mcp add 3d-modeler -- /absolute/path/to/mcp-3d-modeler/.venv/bin/python /absolute/path/to/mcp-3d-modeler/server.py
```

### Running the test loop

```bash
.venv/bin/python tests/test_loop.py
```

This drives the server exactly as a real MCP client would (`stdio_client` +
`ClientSession`, not calling `mcp3d.tools` directly): it generates a
dimensioned bracket via CadQuery, auto-renders it, calls `render_preview`
standalone on the resulting STEP file, runs one check against each of the
other three backends, deliberately breaks a script to confirm errors come
back structured (and the session survives it), and exercises
`convert_format` both directions. Rendered PNGs land in `tests/output/` -
open them and look; a passing exit code only confirms the plumbing, not that
the shapes look right.

## Dependency / environment gotchas hit while building this

- **CadQuery/OCP wheel availability is the real risk, not `bpy`.**
  `cadquery-ocp` and `manifold3d` are OCCT/C++-backed wheels that historically
  lag a Python release by months. This machine's system Python was 3.14.6
  (released weeks before this was built) and cp314 wheels for both already
  existed - but don't assume that; check `pip index versions cadquery-ocp`
  and `pip download --no-deps cadquery-ocp` for your target Python before
  committing to a version. `uv sync` on this project actually resolved to
  Python 3.12 on its own (via `requires-python = ">=3.11"` and its own
  solver), which sidesteps the bleeding-edge-wheel risk entirely - that's a
  feature, not a bug, of not hand-pinning the interpreter.

- **Don't `pip install bpy`.** The `bpy` PyPI package is a separate,
  standalone build of Blender-as-a-library with its own version matrix and
  wheel-availability problems, and it's exactly the thing that conflicts with
  CadQuery's OCP bindings if both end up importable in one process. This
  project never imports `bpy` in the server's own venv at all - it shells
  out to the real, already-installed `blender` binary via `--background
  --python`, which uses Blender's own bundled/linked interpreter. If your
  distro's Blender package happens to link against the system Python (true
  here, both were 3.14.6), that's incidental; the architecture doesn't depend
  on it.

- **`mcp` 2.0.0 dropped `FastMCP` on release day.** `pip index versions mcp`
  showed 2.0.0 as latest, but it restructured the server API and no longer
  exposes `mcp.server.fastmcp`. Given that's a same-day major release with no
  established migration docs yet, this project pins `mcp>=1.29.0,<2.0.0` -
  the stable, widely-documented `FastMCP`/`@mcp.tool()` line. Revisit the pin
  once 2.x has had time to settle and community examples catch up.

- **Blender's Python operator names churn across versions and the change is
  silent (`AttributeError` at call time, not at import time).** On Blender
  5.2 it's `bpy.ops.wm.stl_export` / `wm.obj_export` / `wm.ply_export` /
  `wm.fbx_import`, but `bpy.ops.export_scene.gltf` / `import_scene.gltf` for
  glTF (that one hasn't moved to the `wm` namespace). Older Blender versions
  used `export_mesh.stl` etc. If you're running a different Blender version,
  regenerate this list yourself rather than trusting any hardcoded mapping -
  run a background Python script that walks `dir(bpy.ops.wm)` /
  `dir(bpy.ops.export_scene)` and grep for your formats.

- **`BLENDER_EEVEE_NEXT` isn't a valid render engine on this build; it's
  `BLENDER_EEVEE`.** `scene.render.engine = 'BLENDER_EEVEE_NEXT'` raises
  `TypeError: enum "BLENDER_EEVEE_NEXT" not found in ('BLENDER_EEVEE',
  'BLENDER_WORKBENCH', 'CYCLES')` on this Blender 5.2 build - the "Next"
  rename evidently hasn't landed (or was reverted) in this package build.
  Verify valid enum values on your build (`scene.render.bl_rna.properties['engine'].enum_items.keys()`)
  rather than assuming the newest-sounding name is right. `BLENDER_EEVEE`
  renders correctly fully headless (no X server, no GPU passthrough needed;
  confirmed via `--background`) - no Xvfb, no OSMesa flags, nothing extra
  required on this setup.

- **Every `blender --background` invocation prints unrelated startup noise
  to stderr, which will bury real script errors if you're not careful.** A
  core addon (`bl_pkg`, the extensions manager) tries to import `cattrs` at
  startup and fails with a traceback + `Exception in module register()` on
  every single invocation - success or failure - if `python-cattrs` isn't
  installed system-wide (Blender here links against the system Python and
  its site-packages). This is cosmetic and doesn't affect script execution,
  but it means naively treating "stderr is non-empty" as failure is wrong,
  and it pads every log with several lines a debugging LLM has to skip past
  to find the actual traceback. Fixed here by installing `python-cattrs` (a
  real Arch package: `sudo pacman -S python-cattrs`) - cleaner than teaching
  every caller to filter noise. `--factory-startup` does *not* suppress this;
  `bl_pkg` is a core addon, not a user addon, so it still tries to register.
  Success/failure detection in this project is based on subprocess exit code
  and explicit `OK:`/traceback markers, never on stderr being empty.

- **CadQuery's plain-shape exporter has no OBJ or glTF support**
  (`cq.exporters.export` only knows STL, STEP, AMF, SVG, TJS, DXF, VRML, VTP,
  3MF, BREP, BIN - no OBJ, no glTF for a bare `Workplane`/`Shape`). Only
  `cq.Assembly.save()` can write glTF, and only for assemblies. Requesting
  `output_format="obj"` or `"glb"` from `model_parametric` on a plain shape
  therefore goes through an STL intermediate + a trimesh conversion pass
  automatically (see `tools.py`); it's not a single native export. Same
  story for OpenSCAD (`openscad` CLI has no OBJ/glTF export either) and for
  Blender-organic when the target format isn't one of its native exporters.

- **Mesh → STEP is architecturally not supported, not just "not implemented
  yet."** STEP encodes BREP topology (faces, edges, trimmed surfaces); a
  triangle mesh has none of that, and there's no reliable general algorithm
  to reconstruct it. `convert_format` and `model_organic`/`model_procedural`/
  `model_csg` all reject a STEP output request up front with an explanatory
  error pointing at `model_parametric` instead of attempting something that
  would silently produce garbage BREP or crash deep in OCP.

## Tool-authoring conventions

Each modeling tool expects a specific variable/state convention in the
script it's given, documented in both the tool descriptions (so the calling
LLM sees them) and the runner scripts themselves:

- `model_parametric` (CadQuery): assign the final shape to `result` - a
  `cq.Workplane`, `cq.Shape`, or `cq.Assembly`. `cq` is already in scope.
- `model_procedural` (trimesh): assign the final geometry to `result` - a
  `trimesh.Trimesh`, `trimesh.Scene`, or list of `Trimesh` (auto-combined
  into a Scene). `trimesh` and `np` are already in scope.
- `model_organic` (Blender): no `result` variable - build/modify mesh
  objects with normal `bpy.ops`/`bpy.data` calls against a clean, empty
  scene. Every mesh object present when the script finishes gets exported.
  `bpy` is already in scope.
- `model_csg` (OpenSCAD): plain OpenSCAD source, e.g.
  `difference() { cube([20,20,10]); cylinder(h=12, r=4); }`.
