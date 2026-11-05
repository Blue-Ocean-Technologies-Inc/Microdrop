# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The non-modal Camera Properties window: the selected camera's focus row
and image controls (exposure, brightness, ...), roomier than the sidebar.

Standalone it needs only a CameraModel and its CameraController."""

# Enthought library imports.
from pyface.qt.QtWidgets import QDialog, QVBoxLayout
from traits.api import HasTraits, Instance
from traitsui.api import UI

# Microdrop style imports.
from microdrop_style.button_styles import TEXT_BUTTON_STYLE

# Local imports.
from ...controllers.camera_controller import CameraController
from ...models.camera import CameraModel
from .focus_view import CameraFocusHandler, camera_focus_view
from .image_settings_view import camera_image_settings_view

#: Wide enough for the sliders to be usable.
CAMERA_PROPERTIES_MIN_WIDTH_PX = 480


class CameraPropertiesWindow(HasTraits):
    """Builds the window on first open and keeps it, hidden, between opens."""

    #: The camera panel's state the window views.
    camera_model = Instance(CameraModel)

    #: Applies the focus row's edits (the image controls go through the
    #: model, which the controller observes).
    controller = Instance(CameraController)

    #: The window; None until first opened.
    control = Instance(QDialog)

    #: The focus row.
    focus_ui = Instance(UI)

    #: The image controls.
    image_settings_ui = Instance(UI)

    def open(self, parent=None):
        """Show the window over ``parent`` (built on first call), or raise
        it if it is already open."""

        if self.control is None:
            self.control = self._build(parent)

        self.control.show()
        self.control.raise_()
        self.control.activateWindow()

    def close(self):
        if self.control is not None:
            self.control.hide()

    def _build(self, parent):
        dialog = QDialog(parent)
        dialog.setWindowTitle("Camera Properties")
        dialog.setModal(False)
        dialog.setMinimumWidth(CAMERA_PROPERTIES_MIN_WIDTH_PX)
        layout = QVBoxLayout(dialog)

        self.focus_ui = self.camera_model.focus.edit_traits(
            view=camera_focus_view,
            kind="subpanel",
            parent=dialog,
            handler=CameraFocusHandler(controller=self.controller),
        )
        self.image_settings_ui = self.camera_model.edit_traits(
            view=camera_image_settings_view, kind="subpanel", parent=dialog
        )

        # The Autofocus and Defaults buttons carry real words, so they need
        # the text-button font override against the app's icon-font theme.
        for properties_ui in (self.focus_ui, self.image_settings_ui):
            properties_ui.control.setStyleSheet(TEXT_BUTTON_STYLE)
            layout.addWidget(properties_ui.control)

        layout.addStretch()

        return dialog
