# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!


"""Sidebar section: camera feed controls, the Camera Properties window
button, camera alignment, layer opacity."""

# Enthought library imports.
from pyface.qt.QtWidgets import QHBoxLayout, QPushButton, QWidget
from traits.api import Instance, observe
from traitsui.api import UI

# Microdrop style imports.
from microdrop_style.button_styles import TEXT_BUTTON_STYLE

# Local imports.
from ..alpha_view.alpha_table import alpha_table_view
from ..camera_control_view.properties_window import CameraPropertiesWindow
from ..camera_control_view.widget import CameraControlWidget
from .section import SidebarSection, stack_widgets


class CameraControlsSection(SidebarSection):
    """The Camera Controls section and the parts the pane drives directly."""

    #: Camera feed, capture, and recording controls.
    camera_control_widget = Instance(CameraControlWidget)

    #: The non-modal Camera Properties window (focus, image controls).
    camera_properties_window = Instance(CameraPropertiesWindow)

    #: Opens the Camera Properties window; shown only while the selected
    #: camera has focus or image controls.
    camera_properties_button = Instance(QPushButton)

    #: Layer opacity table UI; the pane sizes it from preferences.
    alpha_view_ui = Instance(UI)

    @observe(
        "camera_properties_button, "
        "camera_properties_window.camera_model.[focus.available,image_settings]"
    )
    def _offer_camera_properties_when_controllable(self, event):
        window = self.camera_properties_window

        if self.camera_properties_button is None or window is None:
            return

        model = window.camera_model
        controllable = model.focus.available or bool(model.image_settings)

        self.camera_properties_button.setVisible(controllable)

        if not controllable:
            window.close()


def build_camera_controls(
    model,
    video_item,
    scene,
    app_preferences,
    status_bar_manager,
    source_providers,
    on_align_camera,
    on_go_to_endpoint,
):
    """Build the Camera Controls section.

    Parameters
    ----------
    status_bar_manager
        Usually still None here: the task creates it after the dock panes,
        and the pane pushes it to the camera widget once it exists.
    source_providers
        Callable returning the camera-source providers other plugins
        contribute.
    on_align_camera, on_go_to_endpoint
        Handlers for the Align Camera and Go To Endpoint buttons.
    """
    alpha_view_ui = model.edit_traits(view=alpha_table_view)

    camera_control_widget = CameraControlWidget(
        model,
        video_item,
        scene,
        app_preferences,
        status_bar_manager=status_bar_manager,
        source_providers=source_providers,
    )

    camera_properties_window = CameraPropertiesWindow(
        camera_model=camera_control_widget.camera_model,
        controller=camera_control_widget.controller,
    )

    properties_widget = QWidget()
    properties_layout = QHBoxLayout(properties_widget)
    camera_properties_button = QPushButton("Camera Properties")
    camera_properties_button.setStyleSheet(TEXT_BUTTON_STYLE)
    camera_properties_button.setToolTip(
        "Focus, exposure and image controls of the selected camera"
    )
    camera_properties_button.clicked.connect(
        lambda: camera_properties_window.open(parent=camera_properties_button.window())
    )
    properties_layout.addWidget(camera_properties_button)

    # Camera Alignment: the manual per-device endpoint workflow.
    # Lives right under the camera-control button grid.
    alignment_widget = QWidget()
    alignment_layout = QHBoxLayout(alignment_widget)
    for label, handler, tip in (
        (
            "Align Camera",
            on_align_camera,
            "Place this device's endpoint on the SVG and drag the "
            "corner dots onto its outline in a captured camera frame",
        ),
        (
            "Go To Endpoint",
            on_go_to_endpoint,
            "Glide the marked points onto this device's saved endpoint",
        ),
    ):
        action_button = QPushButton(label)
        # The sidebar's theme stylesheet renders QPushButton text
        # in the Material Symbols icon font — these buttons carry
        # real words, so they get the text-button font override.
        action_button.setStyleSheet(TEXT_BUTTON_STYLE)
        action_button.setToolTip(tip)
        action_button.clicked.connect(handler)
        alignment_layout.addWidget(action_button, 1)

    widget = stack_widgets(
        [
            camera_control_widget,
            properties_widget,
            alignment_widget,
            alpha_view_ui.control,
        ]
    )

    # Same side margins and gap as the camera-control button rows so
    # the two buttons line up with the four above (each spans a pair);
    # the bottom margin separates them from the alpha table below. The
    # Camera Properties button takes the same side margins.
    # Read only now: Qt's default layout margin is wider for a widget
    # that is still a window than for a child, so it settles once the
    # camera widget sits inside the stack.
    _camera_layout = camera_control_widget.layout()
    _camera_margins = _camera_layout.contentsMargins()
    alignment_layout.setContentsMargins(
        _camera_margins.left(), 0, _camera_margins.right(), 12
    )
    alignment_layout.setSpacing(_camera_layout.spacing())
    properties_layout.setContentsMargins(
        _camera_margins.left(), 0, _camera_margins.right(), _camera_layout.spacing()
    )

    return CameraControlsSection(
        title="Camera Controls",
        widget=widget,
        camera_control_widget=camera_control_widget,
        camera_properties_window=camera_properties_window,
        camera_properties_button=camera_properties_button,
        alpha_view_ui=alpha_view_ui,
    )
