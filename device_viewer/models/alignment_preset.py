# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""One saved camera alignment: the record a preset (and, in later stages, a
history snapshot) persists.

Geometry is kept only in coordinates that survive a restart: the camera
side in RAW camera pixels, the device side in device-scene coordinates.
Video-item coordinates depend on the scene size and the letterbox, so they
are never persisted."""

# Standard library imports.
from datetime import datetime, timezone
from uuid import uuid4

# Enthought library imports.
from traits.api import Float, HasTraits, List, Str, Union

# Local imports.
from ..consts import ALIGNMENT_PRESET_KIND_NAMED, ALIGNMENT_PRESET_SCOPE_DEVICE
from ..utils.quad_order import canonical_quad


def alignment_preset_name_error(name):
    """Return why ``name`` cannot name a preset, or "" when it can.

    Uniqueness is per device and checked by whoever knows the device's
    other presets.
    """
    name = name.strip()

    if not name:
        return "Enter a name for the preset."

    if any(ord(character) < 32 or ord(character) == 127 for character in name):
        return "A preset name cannot contain control characters."

    return ""


def utc_now_iso():
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _quad(value):
    """Return ``value`` as a plain [[x, y] * 4] float list, or ValueError."""

    if value is None or len(value) != 4:
        raise ValueError("a quad needs exactly 4 points")

    return [[float(x), float(y)] for x, y in value]


def _optional_quad(value):
    return None if value is None else _quad(value)


def _optional_floats(value, length):
    """Return ``value`` as a list of ``length`` floats, None for None."""

    if value is None:
        return None

    if len(value) != length:
        raise ValueError(f"expected {length} numbers, got {len(value)}")

    return [float(number) for number in value]


class AlignmentPreset(HasTraits):
    """One saved alignment. Qt-free; ``to_dict``/``from_dict`` are the
    JSON form."""

    #: Stable identity: renames and replacements never re-key a preset,
    #: so a default pointing at it survives both.
    id = Str()

    #: The user's name for it, unique per device (case-insensitively).
    name = Str()

    #: "named" for a user-saved preset; later stages add history snapshots.
    kind = Str(ALIGNMENT_PRESET_KIND_NAMED)

    #: Which setups it applies to: "device" (only its own device) in this
    #: stage; later stages add camera-specific and device-agnostic scopes.
    scope = Str(ALIGNMENT_PRESET_SCOPE_DEVICE)

    #: The device it was saved for — its SVG file's stem.
    device_key = Str()

    #: The device's scene rect at save time as [x, y, w, h]; None when
    #: unknown (presets migrated from the endpoint cache).
    device_scene_rect = Union(None, List(Float))

    #: The selected camera's label at save time; "" when unknown.
    camera_label = Str()

    #: The camera's native frame size at save time as [w, h]; None when
    #: there was no frame.
    frame_size = Union(None, List(Float))

    #: The camera-side corners in RAW camera pixels, in correspondence
    #: order with ``scene_quad``; None for an endpoint-only preset.
    camera_quad = Union(None, List(List(Float)))

    #: Where the camera corners landed in the device scene (the live
    #: transformed reference rect), in correspondence order. Kept apart
    #: from the endpoint: a turned feed or a hand-dragged red frame makes
    #: the two differ.
    scene_quad = List(List(Float))

    #: The device's alignment endpoint (scene coordinates, numbered from
    #: the top-left clockwise).
    endpoint_quad = List(List(Float))

    #: When it was saved, as a UTC ISO 8601 string.
    saved_at = Str()

    def _id_default(self):
        return str(uuid4())

    def _saved_at_default(self):
        return utc_now_iso()

    @property
    def is_endpoint_only(self):
        """Whether the preset carries no camera-side corners."""
        return self.camera_quad is None

    def to_dict(self):
        """Return the record as plain JSON-ready data."""

        def plain(value):
            if value is None:
                return None

            return [plain(item) if isinstance(item, list) else item for item in value]

        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "scope": self.scope,
            "device_key": self.device_key,
            "device_scene_rect": plain(self.device_scene_rect),
            "camera_label": self.camera_label,
            "frame_size": plain(self.frame_size),
            "camera_quad": plain(self.camera_quad),
            "scene_quad": plain(self.scene_quad),
            "endpoint_quad": plain(self.endpoint_quad),
            "saved_at": self.saved_at,
        }

    @classmethod
    def from_dict(cls, data):
        """Return the record ``data`` describes.

        Raises ``ValueError``, ``TypeError`` or ``KeyError`` when it is
        malformed. Keys this version does not know are ignored here; the
        store keeps them on disk.
        """

        if not isinstance(data, dict):
            raise TypeError(f"a preset record is a JSON object, not {data!r}")

        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            kind=str(data.get("kind", ALIGNMENT_PRESET_KIND_NAMED)),
            scope=str(data.get("scope", ALIGNMENT_PRESET_SCOPE_DEVICE)),
            device_key=str(data.get("device_key", "")),
            device_scene_rect=_optional_floats(data.get("device_scene_rect"), 4),
            camera_label=str(data.get("camera_label", "")),
            frame_size=_optional_floats(data.get("frame_size"), 2),
            camera_quad=_optional_quad(data.get("camera_quad")),
            scene_quad=_quad(data["scene_quad"]),
            endpoint_quad=canonical_quad(_quad(data["endpoint_quad"])),
            saved_at=str(data.get("saved_at", "")),
        )
