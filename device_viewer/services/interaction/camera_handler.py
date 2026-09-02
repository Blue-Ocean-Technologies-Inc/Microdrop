# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from pyface.qt.QtCore import QPointF
from pyface.qt.QtGui import QAction
from traits.api import Bool, Instance, Int, List, observe

# Local imports.
from .handler import InteractionHandler

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class CameraInteractionHandler(InteractionHandler):
    """Place and edit the camera perspective's reference rectangle.

    ``camera-place`` collects four corners by clicking; the fourth click
    derives the perspective and switches to ``camera-edit``, where dragging
    a corner reshapes the rectangle — either re-deriving the perspective or,
    with ``edit_reference_rect`` on, only the drawn rectangle.
    """

    modes = ("camera-place", "camera-edit")

    #: Corners placed so far (camera-place), or the copy of the rectangle
    #: being edited without touching the perspective (camera-edit).
    rect_buffer = List(Instance(QPointF), [])

    #: Index of the corner being dragged; -1 when none.
    rect_editing_index = Int(-1)

    #: Edit the reference rect without affecting the perspective.
    edit_reference_rect = Bool(False)

    def on_enter(self, mode, previous_mode):
        if mode == "camera-edit":
            self.electrode_view_layer.redraw_reference_rect(
                self.model.camera_perspective.transformed_reference_rect
            )
        if mode == "camera-place":
            self.rect_buffer.clear()

    def on_exit(self, mode, next_mode):
        if next_mode != "camera-edit":
            self.electrode_view_layer.clear_reference_rect()

    def mouse_press(self, event, electrode_view):
        if self.model.mode == "camera-place":
            self.rect_buffer.append(event.scenePos())
        else:
            _closest_point, closest_index = (
                self.model.camera_perspective.get_closest_point(event.scenePos())
            )
            self.rect_editing_index = closest_index

    def mouse_move(self, event, electrode_view):
        if self.pointer.left_pressed and self.model.mode == "camera-edit":
            self._move_reference_corner(event.scenePos())

    def mouse_release(self, event, electrode_view):
        if self.model.mode == "camera-edit":
            self.rect_editing_index = -1

    def populate_context_menu(self, menu, event):
        def set_camera_place_mode():
            self.model.mode = "camera-place"

        reference_rect_edit_action = QAction(
            "Edit Reference Rect",
            checkable=True,
            checked=self.edit_reference_rect,
            toolTip="Edit Reference Rectangle without changing camera perspective",
        )
        reference_rect_edit_action.triggered.connect(self.toggle_edit_reference_rect)

        menu.addAction("Reset Reference Rectangle", set_camera_place_mode)
        menu.addAction(reference_rect_edit_action)
        menu.addSeparator()
        return True

    def toggle_edit_reference_rect(self):
        if self.edit_reference_rect:
            logger.info(
                "Toggling reference rect edit mode off. Changed will affect "
                "camera perspective"
            )
        else:
            logger.info(
                "Toggling reference rect edit mode on. Changed will not affect "
                "camera perspective"
            )

        self.edit_reference_rect = not self.edit_reference_rect

    def _move_reference_corner(self, point):
        """Move the corner being dragged to ``point``."""
        # check if we are editing just the reference rect buffer or the actual rect
        # tied to transforming perspective
        if self.edit_reference_rect:
            logger.debug("Only reference rect buffer changed")
            if not self.rect_buffer:
                self.rect_buffer = (
                    self.model.camera_perspective.transformed_reference_rect.copy()
                )
            rect_to_edit = self.rect_buffer
        else:
            logger.debug("Reference rect tied to perspective transform changed")
            rect_to_edit = self.model.camera_perspective.transformed_reference_rect

        rect_to_edit[self.rect_editing_index] = point

    @observe("model:camera_perspective:transformed_reference_rect")
    def _reference_rect_change(self, event):
        logger.debug(f"Reference rectangle change: {event}")
        if self.electrode_view_layer and self.model.mode.split("-")[0] == "camera":
            self.electrode_view_layer.redraw_reference_rect(rect=event.new)

    @observe("model:camera_perspective:transformed_reference_rect:items")
    def _reference_rect_items_change(self, event):
        logger.debug(f"Reference rectangle items change: {event}")
        if self.electrode_view_layer and self.model.mode.split("-")[0] == "camera":
            self.electrode_view_layer.redraw_reference_rect(rect=event.object)

    @observe("rect_buffer:items")
    def _rect_buffer_change(self, event):
        logger.debug(
            f"rect_buffer change: adding point {event.added}. "
            f"Buffer of length {len(self.rect_buffer)} now."
        )
        if len(self.rect_buffer) == 4:  # We have a rectangle now
            inverse = self.model.camera_perspective.transformation.inverted()[
                0
            ]  # Get the inverse of the existing transformation matrix
            self.model.camera_perspective.reference_rect = [
                inverse.map(point) for point in event.object
            ]
            self.model.camera_perspective.transformed_reference_rect = (
                self.rect_buffer.copy()
            )

            # User may have already completed the reference rectangle and in edit mode.
            # sometimes user is just editing a completed rect_buffer when
            # edit_reference_rect is enabled
            # Only need to do this and give log message when its the first time the
            # reference rect is completed.
            if self.model.mode != "camera-edit":
                logger.info(
                    "Reference rectangle complete!\n"
                    "Proceed to camera perspective editing!!"
                )
                self.model.mode = (
                    "camera-edit"  # Switch to camera-edit mode if not already there
                )

        else:
            self.electrode_view_layer.redraw_reference_rect(rect=event.object)
