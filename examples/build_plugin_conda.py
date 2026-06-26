"""Build the scipy_analysis demo plugin into a .conda artifact (the install
format). Replaces build_plugin_zip.py — plugins are now conda packages.

Usage: pixi run python examples/build_plugin_conda.py [output_dir]
"""
import subprocess
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent / "demo_plugins" / "scipy_analysis_pkg"


def build(output_dir):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["pixi", "build", "--path", str(PKG),
         "--output-dir", str(out)],
        check=True,
    )
    built = sorted(out.glob("scipy_analysis-*.conda"))
    print(f"built: {built[-1] if built else '(none found)'}")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "dist_plugins")
