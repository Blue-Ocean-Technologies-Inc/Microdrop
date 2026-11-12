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

# Microdrop utils imports.
from microdrop_utils.file_handler import write_atomically

# Local imports.
from ..consts import (
    CAMERA_ENDPOINTS_FILENAME,
    DEVICE_VIEWER_CACHE_DIRNAME,
    ENDPOINTS_UNREADABLE_TEMPLATE,
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
    def _read_all(self):
        """Every stored entry, {} without a file, or None (logged) when the
        file exists but cannot be read."""

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            logger.warning(f"camera endpoints file unreadable ({self.path}): {exc}")

            return None

        if not isinstance(data, dict):
            logger.warning(f"camera endpoints file malformed ({self.path})")

            return None

        return data

    def _readable_entries(self):
        """Every stored entry; an unreadable file reads as none."""
        data = self._read_all()

        return {} if data is None else data

    def _entries_to_rewrite(self):
        """Every stored entry, to change and write back. Raises ``OSError``
        rather than let a write replace a file that could not be read."""
        data = self._read_all()

        if data is None:
            raise OSError(ENDPOINTS_UNREADABLE_TEMPLATE.format(path=self.path))

        return data

    def save(self, device_key: str, scene_quad) -> None:
        """Persist ``scene_quad`` (4 scene-coordinate points) as the
        alignment endpoint for ``device_key``."""
        if not device_key:
            raise ValueError("an endpoint needs a device key")

        quad = _validated_quad(scene_quad)
        data = self._entries_to_rewrite()
        data[device_key] = {
            "scene_quad": quad,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }

        self._write_all(data)
        logger.info(f"saved camera-alignment endpoint for device {device_key!r}")

    def load(self, device_key: str):
        """The saved endpoint quad for ``device_key`` ([[x, y] * 4]),
        or None."""
        entry = self._readable_entries().get(device_key)
        if not isinstance(entry, dict):
            return None
        try:
            return _validated_quad(entry.get("scene_quad"))
        except (ValueError, TypeError):
            logger.warning(
                f"stored endpoint for {device_key!r} is malformed; ignoring it"
            )
            return None

    def saved_at(self, device_key):
        """When ``device_key``'s endpoint was saved (UTC ISO 8601), or ""."""
        entry = self._readable_entries().get(device_key)

        if not isinstance(entry, dict):
            return ""

        return str(entry.get("saved_at", ""))

    def remove(self, device_key: str) -> None:
        data = self._entries_to_rewrite()

        if device_key in data:
            del data[device_key]
            self._write_all(data)

    def _write_all(self, data):
        write_atomically(self.path, json.dumps(data, indent=1).encode("utf-8"))

    def device_keys(self) -> list:
        """Devices that have a stored endpoint."""
        return sorted(self._readable_entries().keys())
