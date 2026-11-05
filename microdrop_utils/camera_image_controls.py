# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A camera's image controls (exposure, brightness, contrast, ...) behind
one interface, for the backends Qt Multimedia has no API for: DirectShow on
Windows (see directshow_camera_controls) and v4l2 controls on Linux (here).

Controls are named as v4l2 names them; IMAGE_CONTROL_LABELS lists the ones
offered, in display order.
"""

# Enthought library imports.
from traits.api import Bool, HasTraits, Int, Interface, Str, provides

# Local imports.
from .v4l2_fps_getter import (
    V4L2_EXPOSURE_AUTO,
    V4L2_EXPOSURE_AUTO_MANUAL,
    V4L2_EXPOSURE_AUTO_ON,
    list_v4l2_controls,
    parse_v4l2_control_fields,
    set_v4l2_controls,
)

#: The exposure control's name; its value's unit depends on the backend
#: (see ICameraImageControls.describe).
EXPOSURE_CONTROL = "exposure_time_absolute"

#: Image controls offered, by v4l2 name, in display order.
IMAGE_CONTROL_LABELS = {
    EXPOSURE_CONTROL: "Exposure",
    "gain": "Gain",
    "brightness": "Brightness",
    "contrast": "Contrast",
    "saturation": "Saturation",
    "hue": "Hue",
    "sharpness": "Sharpness",
    "gamma": "Gamma",
    "white_balance_temperature": "Balance",
    "backlight_compensation": "Backlight",
}

#: v4l2 auto controls of an image control as (name, on value, off value),
#: newest kernel name first.
V4L2_IMAGE_CONTROL_AUTOS = {
    EXPOSURE_CONTROL: (
        (V4L2_EXPOSURE_AUTO, V4L2_EXPOSURE_AUTO_ON, V4L2_EXPOSURE_AUTO_MANUAL),
    ),
    "white_balance_temperature": (
        ("white_balance_automatic", 1, 0),
        ("white_balance_temperature_auto", 1, 0),
    ),
    "gain": (("gain_automatic", 1, 0), ("autogain", 1, 0)),
}


def format_exposure_ms(exposure_ms):
    """An exposure time for display, e.g. "0.49 ms" or "125 ms"."""

    if exposure_ms < 10:
        return f"{exposure_ms:.2f} ms"

    return f"{exposure_ms:.0f} ms"


class ImageControlRange(HasTraits):
    """One image control's range, as the camera reports it."""

    #: v4l2 name, a key of IMAGE_CONTROL_LABELS.
    name = Str()

    low = Int()

    high = Int()

    step = Int(1)

    default = Int()

    #: The control has an automatic mode (exposure, white balance, gain).
    has_auto = Bool(False)


class ICameraImageControls(Interface):
    """A camera's image controls; failures raise RuntimeError."""

    def ranges(self):
        """Return the ImageControlRange of each control the camera has, in
        IMAGE_CONTROL_LABELS order."""

    def get(self, name):
        """Return control ``name``'s ``(value, auto)``."""

    def set(self, name, value, auto=False):
        """Set control ``name`` to ``value``, or to its automatic mode."""

    def describe(self, name, value):
        """Return ``value`` of control ``name`` in real units (e.g. "0.49
        ms" for exposure), or "" when the raw value says it."""


@provides(ICameraImageControls)
class V4l2ImageControls(HasTraits):
    """A Linux camera's image controls, through ``v4l2-ctl``."""

    #: The camera's ``/dev/videoN`` node.
    device_path = Str()

    def ranges(self):
        controls = list_v4l2_controls(self.device_path)
        ranges = []

        for name in IMAGE_CONTROL_LABELS:
            fields = parse_v4l2_control_fields(controls, name)

            if fields is None or "min" not in fields or "max" not in fields:
                continue

            ranges.append(
                ImageControlRange(
                    name=name,
                    low=fields["min"],
                    high=fields["max"],
                    step=fields.get("step", 1),
                    default=fields.get("default", fields["min"]),
                    has_auto=self._auto(controls, name) is not None,
                )
            )

        return ranges

    def get(self, name):
        controls = list_v4l2_controls(self.device_path)
        fields = parse_v4l2_control_fields(controls, name)

        if fields is None or "value" not in fields:
            raise RuntimeError(f"{self.device_path} has no {name} control")

        auto = self._auto(controls, name)
        is_auto = False

        if auto is not None:
            auto_name, _on, off = auto
            is_auto = parse_v4l2_control_fields(controls, auto_name)["value"] != off

        return fields["value"], is_auto

    def set(self, name, value, auto=False):
        controls = {}
        auto_control = self._auto(list_v4l2_controls(self.device_path), name)

        # The manual value is ignored (inactive) while auto is on, so auto
        # goes off before it is written.
        if auto_control is not None:
            auto_name, on, off = auto_control
            controls[auto_name] = on if auto else off

        if not auto:
            controls[name] = int(value)

        if not set_v4l2_controls(self.device_path, **controls):
            raise RuntimeError(f"v4l2 {name} set failed on {self.device_path}")

    def describe(self, name, value):
        # UVC exposure_time_absolute counts 100 µs units.
        if name == EXPOSURE_CONTROL:
            return format_exposure_ms(value / 10)

        return ""

    @staticmethod
    def _auto(controls, name):
        """The (name, on value, off value) of image control ``name``'s
        v4l2 auto control the camera has, or None."""

        for auto in V4L2_IMAGE_CONTROL_AUTOS.get(name, ()):
            fields = parse_v4l2_control_fields(controls, auto[0])

            if fields is not None and "value" in fields:
                return auto

        return None
