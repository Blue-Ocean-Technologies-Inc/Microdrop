# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The image view's keyboard shortcuts, run from KEYBOARD_SHORTCUTS."""

# Enthought library imports.
from traits.api import Callable, Dict, HasTraits, Instance

# Microdrop utils imports.
from microdrop_utils import keyboard_shortcuts

# Local imports.
from ..consts import KEYBOARD_SHORTCUTS, SHORTCUTS_INERT_WHILE_TRACING
from ..model import ImageViewerModel
from .roi_model import RoiAnalysisModel


class RoiShortcutService(HasTraits):
    """Run the image view's keyboard shortcuts from KEYBOARD_SHORTCUTS.

    Qt-light: it reads key events but only drives the viewer and ROI
    analysis models, firing the same button traits the toolbar does, so
    a key and a click are one code path. A handler returns False when it
    did nothing, so the view can pass the key on; any other return value
    means the shortcut ran.
    """

    #: The ROI tool state the analysis toolbar drives.
    analysis_model = Instance(RoiAnalysisModel)

    #: The viewer's navigation, fit and zoom.
    viewer_model = Instance(ImageViewerModel)

    #: Returns True while a contour is being traced on the canvas; None
    #: when no canvas can trace one.
    is_tracing_contour = Callable()

    #: Opens the keyboard shortcut cheat sheet.
    show_shortcuts_handler = Callable()

    #: QKeySequence -> action name, built once from KEYBOARD_SHORTCUTS.
    _actions_by_sequence = Dict()

    def traits_init(self):
        self._actions_by_sequence = keyboard_shortcuts.actions_by_sequence(
            KEYBOARD_SHORTCUTS
        )

    # ------------------ Key events ------------------------------------

    def handle_key_press_event(self, event):
        """Run the shortcut bound to the pressed keys; return True if one ran."""
        action = self._actions_by_sequence.get(
            keyboard_shortcuts.key_sequence_of(event)
        )

        if action is None:
            return False

        if action in SHORTCUTS_INERT_WHILE_TRACING and self._tracing_contour():
            return False

        return self.resolve_action(action)() is not False

    def resolve_action(self, action):
        """Return the callable that runs ``action``, or None if there is none."""
        primary = keyboard_shortcuts.primary_action(action)

        return getattr(self, f"action_{primary}", None)

    def _tracing_contour(self):
        return self.is_tracing_contour is not None and self.is_tracing_contour()

    # ------------------ Draw ------------------------------------------

    def action_draw_ellipse(self):
        self.analysis_model.draw_ellipse_button = True

    def action_draw_box(self):
        self.analysis_model.draw_box_button = True

    def action_draw_capsule(self):
        self.analysis_model.draw_capsule_button = True

    def action_draw_polygon(self):
        self.analysis_model.draw_polygon_button = True

    def action_toggle_negative_mode(self):
        self.analysis_model.negative_mode = not self.analysis_model.negative_mode

    # ------------------ Modes -----------------------------------------

    def action_toggle_edit_mode(self):
        self.analysis_model.edit_mode = not self.analysis_model.edit_mode

    def action_toggle_show_rois(self):
        self.analysis_model.show_rois = not self.analysis_model.show_rois

    def action_escape(self):
        """Leave Esc to the view: the canvas layer, which runs first, puts
        an armed draw tool away. The row is in the table for the sheet."""
        return False

    # ------------------ Images ----------------------------------------

    def action_next_image(self):
        self.viewer_model.next_button = True

    def action_previous_image(self):
        self.viewer_model.previous_button = True

    def action_next_experiment(self):
        self.viewer_model.next_experiment_button = True

    def action_previous_experiment(self):
        self.viewer_model.previous_experiment_button = True

    def action_toggle_exclude_image(self):
        """Flip the sidebar's exclude checkbox for the shown image."""
        analysis = self.analysis_model

        if not analysis.current_image_path:
            return False

        analysis.current_image_excluded = not analysis.current_image_excluded

    # ------------------ Actions ---------------------------------------

    def action_copy_roi(self):
        self.analysis_model.copy_roi_button = True

    def action_paste_roi(self):
        self.analysis_model.paste_roi_button = True

    def action_delete_roi(self):
        self.analysis_model.delete_roi_button = True

    def action_undo(self):
        if not self.analysis_model.can_undo:
            return False

        self.analysis_model.undo_roi_button = True

    def action_redo(self):
        if not self.analysis_model.can_redo:
            return False

        self.analysis_model.redo_roi_button = True

    def action_calculate(self):
        self.analysis_model.calculate_button = True

    # ------------------ View ------------------------------------------

    def action_zoom_in(self):
        self.viewer_model.zoom_request = 1

    def action_zoom_out(self):
        self.viewer_model.zoom_request = -1

    def action_fit_view(self):
        self.viewer_model.fit_request = True

    # ------------------ Help ------------------------------------------

    def action_show_shortcuts(self):
        if self.show_shortcuts_handler is None:
            return False

        self.show_shortcuts_handler()
