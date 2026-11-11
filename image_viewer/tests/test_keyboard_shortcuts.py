# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the image viewer's keyboard shortcut table and dispatch."""

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Microdrop package imports.
from image_viewer.analysis.roi_model import RoiAnalysisModel
from image_viewer.analysis.roi_shortcut_service import RoiShortcutService
from image_viewer.consts import (
    KEYBOARD_SHORTCUT_GROUPS,
    KEYBOARD_SHORTCUTS,
    SHORTCUTS_INERT_WHILE_TRACING,
)
from image_viewer.model import ImageViewerModel

# Microdrop utils imports.
from microdrop_utils.keyboard_shortcuts import cheat_sheet_rows

Qt = QtCore.Qt


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def analysis():
    return RoiAnalysisModel()


@pytest.fixture
def service(analysis):
    return RoiShortcutService(
        analysis_model=analysis,
        viewer_model=ImageViewerModel(roi_analysis=analysis),
    )


def key_event(key, modifiers=Qt.KeyboardModifier.NoModifier):
    return QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, key, modifiers)


def fired(model, trait):
    """Return a list that collects every firing of ``model.trait``."""
    events = []
    model.observe(events.append, trait)

    return events


def test_shortcut_sequences_are_unique():
    sequences = [row[0] for row in KEYBOARD_SHORTCUTS]

    assert len(sequences) == len(set(sequences))


def test_every_row_names_a_known_group():
    assert {row[3] for row in KEYBOARD_SHORTCUTS} <= set(KEYBOARD_SHORTCUT_GROUPS)


def test_every_table_action_resolves_to_a_handler(service):
    for _, action, _, _ in KEYBOARD_SHORTCUTS:
        assert service.resolve_action(action) is not None


def test_inert_while_tracing_names_table_actions():
    assert SHORTCUTS_INERT_WHILE_TRACING <= {row[1] for row in KEYBOARD_SHORTCUTS}


def test_unmatched_key_returns_false(service):
    assert service.handle_key_press_event(key_event(Qt.Key.Key_Q)) is False


def test_draw_letter_fires_its_toolbar_button(service, analysis):
    ellipse_clicks = fired(analysis, "draw_ellipse_button")

    assert service.handle_key_press_event(key_event(Qt.Key.Key_O)) is True
    assert len(ellipse_clicks) == 1


def test_mode_letters_flip_their_toggles(service, analysis):
    service.handle_key_press_event(key_event(Qt.Key.Key_E))
    service.handle_key_press_event(key_event(Qt.Key.Key_M))
    service.handle_key_press_event(key_event(Qt.Key.Key_V))

    assert analysis.edit_mode is True
    assert analysis.negative_mode is True
    assert analysis.show_rois is False


def test_draw_and_mode_letters_are_inert_mid_trace(service, analysis):
    service.is_tracing_contour = lambda: True
    box_clicks = fired(analysis, "draw_box_button")

    assert service.handle_key_press_event(key_event(Qt.Key.Key_B)) is False
    assert service.handle_key_press_event(key_event(Qt.Key.Key_E)) is False
    assert box_clicks == []
    assert analysis.edit_mode is False


def test_navigation_still_runs_mid_trace(service):
    service.is_tracing_contour = lambda: True
    next_clicks = fired(service.viewer_model, "next_button")

    assert service.handle_key_press_event(key_event(Qt.Key.Key_Right)) is True
    assert len(next_clicks) == 1


def test_shift_arrow_steps_the_experiment(service):
    previous_clicks = fired(service.viewer_model, "previous_experiment_button")

    service.handle_key_press_event(
        key_event(Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
    )

    assert len(previous_clicks) == 1


def test_exclude_key_needs_a_shown_image(service, analysis):
    assert service.handle_key_press_event(key_event(Qt.Key.Key_X)) is False
    assert analysis.current_image_excluded is False

    analysis.current_image_path = "frame.png"
    service.handle_key_press_event(key_event(Qt.Key.Key_X))

    assert analysis.current_image_excluded is True


def test_undo_is_inert_with_nothing_to_undo(service, analysis):
    undo_clicks = fired(analysis, "undo_roi_button")

    handled = service.handle_key_press_event(
        key_event(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    )

    assert handled is False
    assert undo_clicks == []


def test_escape_is_left_to_the_view(service):
    assert service.handle_key_press_event(key_event(Qt.Key.Key_Escape)) is False


def test_cheat_sheet_folds_alternate_keys_into_one_row():
    rows = dict(cheat_sheet_rows(KEYBOARD_SHORTCUTS, KEYBOARD_SHORTCUT_GROUPS))

    assert any(key == "F1 / Ctrl+/" for key, _ in rows["Help"])
    assert any(key == "Ctrl+Y / Ctrl+Shift+Z" for key, _ in rows["Actions"])
