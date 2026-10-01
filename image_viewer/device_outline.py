# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The perspective window's device-outline alignment reference: which
device's electrodes to draw over the frame, and in what colour and
opacity. Qt-free; the settings load from the viewer preferences and every
edit writes straight back, so the choice persists across sessions."""

# Standard library imports.
from pathlib import Path
from xml.etree.ElementTree import ParseError

# Third-party imports.
import numpy as np
from redis.exceptions import RedisError

# Enthought library imports.
from traits.api import (
    Dict,
    HasTraits,
    Instance,
    List,
    Property,
    Range,
    Str,
    cached_property,
    observe,
)
from traitsui.api import RGBColor

# Microdrop package imports.
from device_viewer.consts import DEVICE_REPO_DIR_KEY, MASTER_SVG_FILE
from microdrop_application.helpers import get_microdrop_redis_globals_manager

# Microdrop utils imports.
from microdrop_utils.color_helpers import hex_to_rgb, rgb_to_hex
from microdrop_utils.svg_outline import device_electrode_polygons, list_device_svgs

# Local imports.
from .consts import (
    DEVICE_OUTLINE_ALPHA_BOUNDS_PCT,
    NO_DEVICE_OUTLINE_LABEL,
    PERSISTED_DEVICE_OUTLINE_TRAITS,
)
from .preferences import ImageViewerPreferences

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def published_device_repo_dir():
    """The device viewer's device-SVG repo directory from app globals, ''
    when it has not published one or Redis is unreachable."""
    try:
        return get_microdrop_redis_globals_manager().get(DEVICE_REPO_DIR_KEY) or ""

    except RedisError as e:
        logger.warning(f"No device repo directory from app globals: {e}")

        return ""


class DeviceOutlineReference(HasTraits):
    """A device's electrode outline drawn over the perspective window as a
    fixed target to drag the quad's corners against."""

    #: The viewer preferences the choice persists in.
    preferences = Instance(ImageViewerPreferences, ())

    #: The user's device-SVG repo directory (published_device_repo_dir).
    repo_dir = Str()

    #: The dropdown's choices: device SVG path -> label, '' for no outline.
    #: Labels carry an index prefix that EnumEditor sorts on and hides, so
    #: "None" leads and the devices follow by name.
    devices = Property(Dict(Str, Str), observe="repo_dir")

    #: The chosen device SVG ('' for none).
    svg_path = Str()

    #: Outline opacity, as a percentage.
    alpha = Range(*DEVICE_OUTLINE_ALPHA_BOUNDS_PCT)

    color = RGBColor()

    #: The chosen device's electrode polygons in SVG mm ([] for none).
    polygons = Property(List, observe="svg_path")

    # ------------------------------------------------------------------ #
    # Defaults: read from the preferences without echoing a write back     #
    # ------------------------------------------------------------------ #
    def _svg_path_default(self):
        svg_path = self.preferences.device_outline_svg

        # A device no longer listed (deleted, or the repo moved) draws none.
        return svg_path if svg_path in self.devices else ""

    def _alpha_default(self):
        return self.preferences.device_outline_alpha

    def _color_default(self):
        return hex_to_rgb(self.preferences.device_outline_color)

    @observe(", ".join(PERSISTED_DEVICE_OUTLINE_TRAITS))
    def _persist_setting(self, event):
        value = rgb_to_hex(event.new) if event.name == "color" else event.new

        self.preferences.trait_set(
            **{PERSISTED_DEVICE_OUTLINE_TRAITS[event.name]: value}
        )

    # ------------------------------------------------------------------ #
    # Devices and geometry                                                 #
    # ------------------------------------------------------------------ #
    def device_directory(self):
        """The directory devices are listed from: the user's repo, or the
        bundled devices when it is unset or missing."""

        if not self.repo_dir:
            logger.info(
                f"No device repo directory published; listing the bundled "
                f"devices in {MASTER_SVG_FILE.parent}"
            )

            return MASTER_SVG_FILE.parent

        if not Path(self.repo_dir).is_dir():
            logger.info(
                f"Device repo directory {self.repo_dir} is missing; listing the "
                f"bundled devices in {MASTER_SVG_FILE.parent}"
            )

            return MASTER_SVG_FILE.parent

        logger.info(f"Listing device outlines from the device repo {self.repo_dir}")

        return Path(self.repo_dir)

    @cached_property
    def _get_devices(self):
        devices = {"": f"{0:03d}:{NO_DEVICE_OUTLINE_LABEL}"}
        svg_files = list_device_svgs(self.device_directory())

        for index, svg_file in enumerate(svg_files, start=1):
            devices[str(svg_file)] = f"{index:03d}:{svg_file.stem}"

        return devices

    @cached_property
    def _get_polygons(self):
        if not self.svg_path:
            return []

        try:
            return device_electrode_polygons(self.svg_path)

        except (OSError, ParseError, ValueError) as e:
            logger.error(f"Could not read the device outline {self.svg_path}: {e}")

            return []

    def outline_rings(self, width, height):
        """Each electrode's boundary as an (N, 2) vertex array in frame
        pixels: the whole device scaled to fit a ``width`` x ``height``
        frame, aspect kept, and centred in it."""

        if not self.polygons:
            return []

        rings = [np.asarray(polygon.exterior.coords) for polygon in self.polygons]
        points = np.vstack(rings)
        low = points.min(axis=0)
        size = points.max(axis=0) - low

        scale = min(width / size[0], height / size[1])
        offset = (np.array([width, height]) - size * scale) / 2

        return [(ring - low) * scale + offset for ring in rings]
