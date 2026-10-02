# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Per-device camera-alignment endpoints.

The user defines the ground truth ONCE per device: position the four
alignment points where they belong (finish any good alignment) and
save the endpoint; the scene positions persist. Every later
alignment is then just: mark the start points on the feed and go to
the endpoint — the four precise drags happen automatically.

Endpoints are cached on a device-to-device basis (keyed by the
device SVG's stem) in one JSON file in the device viewer's cache
directory under ETSConfig.application_home, so they survive restarts
and device switches.
"""

# Standard library imports.
import json
from datetime import datetime, timezone
from pathlib import Path

# Enthought library imports.
from traits.etsconfig.api import ETSConfig

# Local imports.
from ..consts import (
    CAMERA_ENDPOINTS_FILENAME,
    DEVICE_VIEWER_CACHE_DIRNAME,
)
from .quad_order import canonical_quad

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def default_endpoints_file() -> Path:
    """Where the per-device endpoints live by default. Resolved at call
    time, after the application has configured ETSConfig."""
    return (
        Path(ETSConfig.application_home)
        / DEVICE_VIEWER_CACHE_DIRNAME
        / CAMERA_ENDPOINTS_FILENAME
    )


def _validated_quad(scene_quad) -> list:
    """The quad as a plain [[x, y] * 4] float list numbered from the
    top-left clockwise (whatever order it was placed or stored in), or
    ValueError."""
    if scene_quad is None or len(scene_quad) != 4:
        raise ValueError("an endpoint needs exactly 4 points")
    quad = []
    for point in scene_quad:
        x, y = point
        quad.append([float(x), float(y)])
    return canonical_quad(quad)


class CameraEndpointStore:
    """Load/save the per-device alignment endpoints (scene-space
    quads, always TL/TR/BR/BL: older entries in another order load
    canonical and are rewritten canonical on the next save)."""

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else default_endpoints_file()

    # ------------------------------------------------------------------ #
    def _read_all(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as exc:
            logger.warning(f"camera endpoints file unreadable ({self.path}): {exc}")
            return {}

    def save(self, device_key: str, scene_quad) -> None:
        """Persist ``scene_quad`` (4 scene-coordinate points) as the
        alignment endpoint for ``device_key``."""
        if not device_key:
            raise ValueError("an endpoint needs a device key")
        quad = _validated_quad(scene_quad)
        data = self._read_all()
        data[device_key] = {
            "scene_quad": quad,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=1), encoding="utf-8")
        logger.info(f"saved camera-alignment endpoint for device {device_key!r}")

    def load(self, device_key: str):
        """The saved endpoint quad for ``device_key`` ([[x, y] * 4]),
        or None."""
        entry = self._read_all().get(device_key)
        if not isinstance(entry, dict):
            return None
        try:
            return _validated_quad(entry.get("scene_quad"))
        except (ValueError, TypeError):
            logger.warning(
                f"stored endpoint for {device_key!r} is malformed; ignoring it"
            )
            return None

    def remove(self, device_key: str) -> None:
        data = self._read_all()
        if device_key in data:
            del data[device_key]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, indent=1), encoding="utf-8")

    def device_keys(self) -> list:
        """Devices that have a stored endpoint."""
        return sorted(self._read_all().keys())
