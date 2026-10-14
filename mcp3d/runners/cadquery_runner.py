"""Standalone script executed via `<venv>/bin/python cadquery_runner.py ...`.

Not imported by the MCP server process. Runs arbitrary CadQuery script text
supplied by the calling LLM, then exports the resulting shape/assembly.

Usage: cadquery_runner.py <script_path> <output_path> <export_type>

Convention the user script must follow: build geometry using the `cq` module
(already in scope) and assign the final shape/assembly to a module-level
variable named `result`. `result` may be a cq.Workplane, cq.Shape, or
cq.Assembly.
"""

from __future__ import annotations

import sys
import traceback

import cadquery as cq

ASSEMBLY_EXPORT_TYPES = {"STEP", "XML", "XBF", "GLTF", "VTKJS", "VRML", "STL"}


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: cadquery_runner.py <script_path> <output_path> <export_type>", file=sys.stderr)
        return 2

    script_path, output_path, export_type = sys.argv[1], sys.argv[2], sys.argv[3]

    with open(script_path, encoding="utf-8") as f:
        code = f.read()

    namespace: dict = {"cq": cq, "cadquery": cq}
    try:
        exec(compile(code, script_path, "exec"), namespace)
    except Exception:
        print("Script raised an exception while executing:", file=sys.stderr)
        traceback.print_exc()
        return 1

    result = namespace.get("result")
    if result is None:
        print(
            "ERROR: script did not define a variable named `result`. "
            "Build your geometry with cq.Workplane(...) (or cq.Assembly() for "
            "multi-part models) and assign the final object to `result`.",
            file=sys.stderr,
        )
        return 1

    try:
        if isinstance(result, cq.Assembly):
            if export_type not in ASSEMBLY_EXPORT_TYPES:
                print(
                    f"ERROR: cq.Assembly results can only be exported as one of "
                    f"{sorted(ASSEMBLY_EXPORT_TYPES)}, not {export_type}. "
                    "For other mesh formats, export STL/STEP here and convert "
                    "separately with convert_format.",
                    file=sys.stderr,
                )
                return 1
            result.save(output_path, exportType=export_type)
        else:
            cq.exporters.export(result, output_path, exportType=export_type)
    except Exception:
        print("Export failed:", file=sys.stderr)
        traceback.print_exc()
        return 1

    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
