"""Build the magnet demo archive:
examples/plugins/magnet_peripherals.microdrop_plugin.

Zips the three magnet packages from src/ plus the bundled
default_plugins/magnet_peripherals/microdrop_plugin.json manifest into the
.microdrop_plugin archive — the canonical example of the install format. Test
directories and bytecode are excluded so the archive matches the installer's
allowlist (only the declared packages + the manifest)."""

import zipfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]                      # src/
MANIFEST = SRC / "default_plugins" / "magnet_peripherals" / "microdrop_plugin.json"
OUT_DIR = SRC / "examples" / "plugins"
OUT = OUT_DIR / "magnet_peripherals.microdrop_plugin"
PACKAGES = ["peripheral_controller", "peripheral_protocol_controls", "peripherals_ui"]


def build():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(MANIFEST, "microdrop_plugin.json")
        for pkg in PACKAGES:
            for path in sorted((SRC / pkg).rglob("*")):
                if path.is_dir():
                    continue
                rel_parts = path.relative_to(SRC).parts
                if "__pycache__" in rel_parts or "tests" in rel_parts:
                    continue
                if path.suffix == ".pyc":
                    continue
                zf.write(path, str(path.relative_to(SRC)))
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
