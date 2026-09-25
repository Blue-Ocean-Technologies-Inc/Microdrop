# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The live camera as the Qt-free CameraController sees it.

The Qt implementation (QCamera + QMediaCaptureSession) lives in the view
layer; tests drive the controller with a stub providing this interface.
"""

# Enthought library imports.
from traits.api import Interface


class ICameraDevice(Interface):
    def has_camera(self):
        """Return whether a camera is bound to the capture session."""

    def is_active(self):
        """Return whether the bound camera is streaming."""

    def supports_manual_exposure(self):
        """Return whether the camera accepts a manual exposure time."""

    def set_auto_exposure(self):
        """Switch the camera to automatic exposure."""

    def set_manual_exposure(self, exposure_ms):
        """Switch the camera to manual exposure at ``exposure_ms``."""

    def exposure_is_manual(self):
        """Return whether the camera is in manual exposure mode."""

    def exposure_time_ms(self):
        """Return the exposure in use right now, auto's pick included;
        zero or negative when the camera does not report it."""

    def manual_exposure_time_ms(self):
        """Return the configured manual exposure time."""

    def supports_manual_focus(self):
        """Return whether the camera accepts a manual focus distance."""

    def set_auto_focus(self):
        """Switch the camera to continuous auto focus."""

    def set_manual_focus(self, focus_distance):
        """Switch to manual focus at ``focus_distance`` (0.0 near, 1.0 far)."""

    def focus_is_manual(self):
        """Return whether the camera is in manual focus mode."""

    def focus_distance(self):
        """Return the camera's focus distance (0.0 near, 1.0 far)."""
