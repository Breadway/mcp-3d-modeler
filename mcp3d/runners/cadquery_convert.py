"""Standalone script executed via `<venv>/bin/python cadquery_convert.py ...`.

Handles conversions where STEP is the *source* format: STEP carries real
BREP topology, so CadQuery/OCP can import it and re-tessellate/re-export to
whatever target format is requested (including STEP -> STEP for a clean
round-trip). There is no equivalent script for mesh -> STEP: a triangle mesh
has no BREP topology to reconstruct, so that direction is rejected up front
by the convert_format tool with an explanatory error rather than attempted
here.

Usage: cadquery_convert.py <input_step_path> <output_path> <export_type>
"""

from __future__ import annotations

import sys
import traceback

import cadquery as cq


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: cadquery_convert.py <input_step_path> <output_path> <export_type>", file=sys.stderr)
        return 2

    input_path, output_path, export_type = sys.argv[1], sys.argv[2], sys.argv[3]

    try:
        shape = cq.importers.importStep(input_path)
    except Exception:
        print(f"Failed to import STEP file {input_path}:", file=sys.stderr)
        traceback.print_exc()
        return 1

    try:
        cq.exporters.export(shape, output_path, exportType=export_type)
    except Exception:
        print("Export failed:", file=sys.stderr)
        traceback.print_exc()
        return 1

    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
