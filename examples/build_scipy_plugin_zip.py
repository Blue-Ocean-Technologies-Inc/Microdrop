"""Build the scipy-analysis demo archive:
examples/plugins/scipy_analysis.microdrop_plugin.

Unlike the magnet demo (whose code lives in src/ and is bundled), this demo
plugin is fully self-contained under examples/demo_plugins/scipy_analysis/ — its
package, manifest, and a pyproject.toml declaring the scipy dependency. scipy is
deliberately absent from MicroDrop's base environment, so installing the archive
exercises the dependency-aware install + relaunch flow.

The archive layout matches the installer allowlist (only the declared package +
the manifest + pyproject.toml):
    microdrop_plugin.json
    pyproject.toml
    scipy_analysis/...
"""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "demo_plugins" / "scipy_analysis"
MANIFEST = ROOT / "microdrop_plugin.json"
PYPROJECT = ROOT / "pyproject.toml"
PKG_DIR = ROOT / "scipy_analysis"
OUT_DIR = Path(__file__).resolve().parent / "plugins"
OUT = OUT_DIR / "scipy_analysis.microdrop_plugin"


def build():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(MANIFEST, "microdrop_plugin.json")
        zf.write(PYPROJECT, "pyproject.toml")
        for path in sorted(PKG_DIR.rglob("*")):
            if path.is_dir():
                continue
            rel_parts = path.relative_to(ROOT).parts
            if "__pycache__" in rel_parts or path.suffix == ".pyc":
                continue
            zf.write(path, str(path.relative_to(ROOT)))
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
