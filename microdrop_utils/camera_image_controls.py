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
Windows (see directshow_camera_controls), and on Linux v4l2 controls and a
Raspberry Pi CSI camera's libcamera controls (here).

Controls are named as v4l2 names them; IMAGE_CONTROL_LABELS lists the ones
offered, in display order.
"""

# Enthought library imports.
from traits.api import Bool, Float, HasTraits, Int, Interface, Str, provides

# Local imports.
from .libcamera_gst_element import (
    get_element_property,
    has_element,
    set_element_property,
    stored_element_property,
)
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

#: libcamerasrc's ``*-mode`` enum nicks.
LIBCAMERA_MODE_AUTO = "auto"
LIBCAMERA_MODE_MANUAL = "manual"


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


class LibcameraImageControl(HasTraits):
    """How one image control maps onto a libcamerasrc property: the panel's
    integer slider runs over the property's value times ``scale``."""

    #: The libcamerasrc property, e.g. "analogue-gain".
    property_name = Str()

    #: Its ``*-mode`` enum property (auto / manual); "" when it has none.
    mode_property_name = Str()

    #: libcamera's range and default, in the property's own units.
    low = Float()

    high = Float()

    default = Float()

    #: Slider steps per property unit.
    scale = Int(1)

    def slider_value(self, value):
        return round(value * self.scale)

    def property_value(self, slider_value):
        return slider_value / self.scale

    def control_range(self, name):
        return ImageControlRange(
            name=name,
            low=self.slider_value(self.low),
            high=self.slider_value(self.high),
            default=self.slider_value(self.default),
            has_auto=bool(self.mode_property_name),
        )


#: The libcamerasrc image controls offered, by v4l2 name. The element's own
#: ranges are unbounded, so these are libcamera's ControlInfo limits, with
#: contrast, saturation and sharpness trimmed to their useful span.
#: libcamerasrc has no colour temperature, so white balance is left to AWB.
LIBCAMERA_IMAGE_CONTROLS = {
    EXPOSURE_CONTROL: LibcameraImageControl(
        property_name="exposure-time",
        mode_property_name="exposure-time-mode",
        low=1,
        high=66666,
        default=20000,
    ),
    "gain": LibcameraImageControl(
        property_name="analogue-gain",
        mode_property_name="analogue-gain-mode",
        low=1.0,
        high=16.0,
        default=1.0,
        scale=100,
    ),
    "brightness": LibcameraImageControl(
        property_name="brightness", low=-1.0, high=1.0, default=0.0, scale=100
    ),
    "contrast": LibcameraImageControl(
        property_name="contrast", low=0.0, high=2.0, default=1.0, scale=100
    ),
    "saturation": LibcameraImageControl(
        property_name="saturation", low=0.0, high=2.0, default=1.0, scale=100
    ),
    "sharpness": LibcameraImageControl(
        property_name="sharpness", low=0.0, high=4.0, default=1.0, scale=100
    ),
}


@provides(ICameraImageControls)
class LibcameraImageControls(HasTraits):
    """A Raspberry Pi CSI camera's image controls, as properties of the
    libcamerasrc element Qt's GStreamer backend builds for it.

    libcamerasrc applies its properties only as the camera starts, so a
    value set here takes effect at the camera's next start, and is kept for
    every camera started after (see libcamera_gst_element)."""

    def ranges(self):
        return [
            LIBCAMERA_IMAGE_CONTROLS[name].control_range(name)
            for name in IMAGE_CONTROL_LABELS
            if name in LIBCAMERA_IMAGE_CONTROLS
        ]

    def get(self, name):
        control = self._control(name)
        auto = bool(control.mode_property_name) and (
            stored_element_property(control.mode_property_name, LIBCAMERA_MODE_AUTO)
            == LIBCAMERA_MODE_AUTO
        )
        value = stored_element_property(control.property_name, control.default)

        # Under auto, libcamera's algorithms drive the control; the element
        # reports the value in use from the frames' metadata.
        if auto and has_element():
            live = get_element_property(control.property_name)

            if live > 0:
                value = live

        return control.slider_value(value), auto

    def set(self, name, value, auto=False):
        control = self._control(name)

        # The value only applies while the mode is manual. ae-enable is no
        # substitute: switching it back on leaves the modes manual.
        if control.mode_property_name:
            mode = LIBCAMERA_MODE_AUTO if auto else LIBCAMERA_MODE_MANUAL
            set_element_property(control.mode_property_name, mode)

        if not auto:
            set_element_property(control.property_name, control.property_value(value))

    def describe(self, name, value):
        control = LIBCAMERA_IMAGE_CONTROLS.get(name)

        if control is None:
            return ""

        if name == EXPOSURE_CONTROL:
            return format_exposure_ms(control.property_value(value) / 1000)

        return f"{control.property_value(value):.2f}"

    @staticmethod
    def _control(name):
        control = LIBCAMERA_IMAGE_CONTROLS.get(name)

        if control is None:
            raise RuntimeError(f"libcamera has no {name} control")

        return control
