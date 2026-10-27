# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Controller-level tests for the ROI editing ergonomics: draw tools
that stay armed, copying a shape into a new ROI, and undo/redo."""

# Standard library imports.
import csv
import math

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences.api import Preferences
from pyface.api import YES

# Microdrop package imports.
from image_viewer.analysis import roi_controller
from image_viewer.analysis.consts import (
    DEFAULT_ROI_COLORS,
    NEGATIVE_MASK_COLOR,
    PASTE_OFFSET_PX,
    ROI_DELETE_BUTTON_SCOPES,
)
from image_viewer.analysis.roi_batch import (
    RoiBatchRunner,
)
from image_viewer.analysis.roi_controller import (
    RoiAnalysisController,
)
from image_viewer.analysis.roi_model import (
    Roi,
    RoiAnalysisModel,
)
from image_viewer.analysis.sam_detect import Candidate
from image_viewer.discovery import capture_timestamp
from image_viewer.model import (
    ImageViewerModel,
)
from image_viewer.preferences import ImageViewerPreferences


def _controller():
    """A controller over its own analysis model: the one the viewer
    model hands out is an app-wide singleton, so tests sharing it would
    inherit each other's ROIs."""
    return RoiAnalysisController(
        viewer_model=ImageViewerModel(), analysis_model=RoiAnalysisModel()
    )


def test_a_drawn_roi_leaves_the_tool_armed():
    controller = _controller()
    model = controller.analysis_model
    model.draw_ellipse_button = True
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])

    assert model.interaction_mode == "draw_ellipse"
    model.canvas_roi_created = ("ellipse", [40.0, 10.0, 5.0, 5.0, 0.0])
    assert len(controller.session.rois) == 2
    assert [roi.name for roi in controller.session.rois] == ["ROI 1", "ROI 2"]


def test_clicking_the_armed_tool_puts_it_away():
    # Its button shows itself pressed, so a second click must release
    # it rather than re-arm what is already armed.
    controller = _controller()
    model = controller.analysis_model
    model.draw_capsule_button = True
    assert model.interaction_mode == "draw_capsule"
    model.draw_capsule_button = True
    assert model.interaction_mode == "pan"

    model.draw_capsule_button = True
    model.draw_box_button = True  # a different tool just switches
    assert model.interaction_mode == "draw_box"


def test_escaping_a_draw_tool_returns_to_the_resting_mode():
    controller = _controller()
    model = controller.analysis_model
    model.draw_box_button = True
    model.canvas_draw_cancelled = True
    assert model.interaction_mode == "pan"

    model.edit_mode = True  # resting mode follows the toggle
    model.draw_box_button = True
    model.canvas_draw_cancelled = True
    assert model.interaction_mode == "edit"


def test_copy_and_paste_offsets_the_shape_and_renames_it():
    controller = _controller()
    model = controller.analysis_model
    model.canvas_roi_created = ("box", [10.0, 20.0, 30.0, 40.0, 0.0, 5.0])
    (original,) = controller.session.rois
    model.selected_roi_id = original.roi_id

    model.copy_roi_button = True
    model.paste_roi_button = True

    original, pasted = controller.session.rois
    assert pasted.kind == "box"
    assert pasted.geometry == [
        10.0 + PASTE_OFFSET_PX,
        20.0 + PASTE_OFFSET_PX,
        30.0,
        40.0,
        0.0,
        5.0,
    ]
    assert pasted.name == "ROI 2"
    assert pasted.roi_id != original.roi_id
    # A shared colour would make the two curves indistinguishable.
    assert pasted.style.color != original.style.color
    assert model.selected_roi_id == pasted.roi_id


def test_one_copy_seeds_repeated_pastes():
    controller = _controller()
    model = controller.analysis_model
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    model.selected_roi_id = controller.session.rois[0].roi_id
    model.copy_roi_button = True

    model.paste_roi_button = True
    model.paste_roi_button = True
    assert len(controller.session.rois) == 3
    # Each paste offsets from the copied shape, not from the last
    # paste, so repeated pastes stack in one place by design.
    assert controller.session.rois[1].geometry == controller.session.rois[2].geometry


@pytest.mark.parametrize("button", list(ROI_DELETE_BUTTON_SCOPES))
def test_delete_removes_the_selected_roi_and_says_so_when_there_is_none(button):
    # No image shown: every delete button removes the ROI outright.
    controller = _controller()
    model = controller.analysis_model
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    model.selected_roi_id = controller.session.rois[0].roi_id

    setattr(model, button, True)
    assert controller.session.rois == []
    assert model.selected_roi_id == ""

    setattr(model, button, True)
    assert "Select an ROI" in model.progress_text


def test_copy_with_nothing_selected_and_paste_with_nothing_copied():
    controller = _controller()
    model = controller.analysis_model

    model.copy_roi_button = True
    assert model.clipboard_kind == ""
    assert "Select an ROI" in model.progress_text

    model.paste_roi_button = True
    assert controller.session.rois == []
    assert model.progress_text == "Nothing copied yet"


def test_saved_fit_presets_load_whichever_order_the_models_arrive():
    # Both models are constructor arguments and traits assigns them one
    # at a time, so the observer has to wait for the second. The pane
    # passes viewer_model first, which is the order that used to raise
    # inside the notifier and quietly leave the dropdown empty.
    from image_viewer.analysis.fit_presets import (
        save_presets,
    )

    viewer = ImageViewerModel()
    viewer.preferences.fit_presets = save_presets([("Bleach", "a*exp(-b*x) + c")])
    for kwargs in (
        dict(viewer_model=viewer, analysis_model=RoiAnalysisModel()),
        dict(analysis_model=RoiAnalysisModel(), viewer_model=viewer),
    ):
        controller = RoiAnalysisController(**kwargs)
        assert [name for name, _text in controller.analysis_model.fit_presets] == [
            "Bleach"
        ]


def test_toggling_a_correction_redraws_from_its_cached_stats():
    """Stats for both correction states can already be cached, so
    Calculate computes nothing; the toggle itself must refresh the plot
    and table (they redraw on stats_revision)."""
    controller = _controller()
    session = controller.analysis_model.session
    session.perspective.trait_set(
        source_quad=[(0, 0), (10, 0), (10, 10), (0, 10)],
        target_quad=[(0, 0), (12, 0), (10, 10), (0, 10)],
    )
    revision = session.stats_revision

    controller.analysis_model.perspective_enabled = True
    assert session.stats_revision > revision

    revision = session.stats_revision
    controller.analysis_model.perspective_enabled = False
    assert session.stats_revision > revision


class _RecordingRunner(RoiBatchRunner):
    """Records the instant computes instead of running them."""

    def __init__(self, **traits):
        super().__init__(**traits)
        self.instant = []

    def compute_single(self, path, effective_rois, correction):
        self.instant.append((path, dict(effective_rois), correction))


def _controller_on_image(tmp_path):
    image = tmp_path / "a_2026_07_20-10_00_00_raw.png"
    image.write_bytes(b"")
    # Preferences of its own, in memory: nothing the controller stores
    # may leak into the next test through the shared default.
    preferences = ImageViewerPreferences(preferences=Preferences())
    controller = RoiAnalysisController(
        viewer_model=ImageViewerModel(preferences=preferences),
        analysis_model=RoiAnalysisModel(),
        runner=_RecordingRunner(),
    )
    controller.viewer_model.current_path = str(image)
    return controller, str(image)


def test_negative_mode_draws_masks_outside_the_colour_cycle():
    controller = _controller()
    model = controller.analysis_model
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    model.negative_mode = True
    model.canvas_roi_created = ("ellipse", [12.0, 10.0, 3.0, 3.0, 0.0])
    model.negative_mode = False
    model.canvas_roi_created = ("ellipse", [40.0, 10.0, 5.0, 5.0, 0.0])

    first, mask, second = controller.session.rois
    assert mask.is_negative and mask.name == "Mask 1"
    assert mask.style.color == NEGATIVE_MASK_COLOR
    assert not first.is_negative and not second.is_negative
    assert second.name == "ROI 2"
    # The mask took no slot: the second ROI gets the second colour.
    assert second.style.color == DEFAULT_ROI_COLORS[1]


def test_a_pasted_mask_stays_a_mask_whatever_the_toggle():
    controller = _controller()
    model = controller.analysis_model
    model.negative_mode = True
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    model.negative_mode = False
    model.selected_roi_id = controller.session.rois[0].roi_id

    model.copy_roi_button = True
    model.paste_roi_button = True

    _original, pasted = controller.session.rois
    assert pasted.is_negative
    assert pasted.name == "Mask 2"
    assert pasted.style.color == NEGATIVE_MASK_COLOR


def test_changing_a_mask_remeasures_every_roi_on_the_image(tmp_path):
    controller, image = _controller_on_image(tmp_path)
    model = controller.analysis_model
    runner = controller.runner
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    model.canvas_roi_created = ("ellipse", [40.0, 10.0, 5.0, 5.0, 0.0])
    positives = {roi.roi_id for roi in controller.session.rois}
    runner.instant.clear()

    model.negative_mode = True
    model.canvas_roi_created = ("ellipse", [12.0, 10.0, 3.0, 3.0, 0.0])
    mask = controller.session.rois[-1]
    (created,) = runner.instant
    assert created[0] == image
    assert set(created[1]) == positives, "one compute, positives only"
    assert created[2][4] == (("ellipse", (12.0, 10.0, 3.0, 3.0, 0.0)),)

    runner.instant.clear()
    model.canvas_roi_edited = (mask.roi_id, [14.0, 10.0, 3.0, 3.0, 0.0])
    (edited,) = runner.instant
    assert set(edited[1]) == positives
    assert edited[2][4] == (("ellipse", (14.0, 10.0, 3.0, 3.0, 0.0)),)

    runner.instant.clear()
    model.selected_roi_id = mask.roi_id
    model.delete_roi_button = True
    (deleted,) = runner.instant
    assert set(deleted[1]) == positives
    assert deleted[2][4] == ()


def test_a_masks_eye_remeasures_and_a_positives_does_not(tmp_path):
    controller, image = _controller_on_image(tmp_path)
    model = controller.analysis_model
    session = controller.session
    runner = controller.runner
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    model.canvas_roi_created = ("ellipse", [40.0, 10.0, 5.0, 5.0, 0.0])
    model.negative_mode = True
    model.canvas_roi_created = ("ellipse", [12.0, 10.0, 3.0, 3.0, 0.0])
    first, _second, mask = session.rois
    positives = {roi.roi_id for roi in session.positive_rois}
    runner.instant.clear()
    revision = session.stats_revision

    mask.style.visible = False
    (hidden,) = runner.instant
    assert hidden[0] == image
    assert set(hidden[1]) == positives, "one compute, positives only"
    assert hidden[2][4] == ()
    assert session.stats_revision > revision

    runner.instant.clear()
    mask.style.visible = True
    (shown,) = runner.instant
    assert set(shown[1]) == positives
    assert shown[2][4] == (("ellipse", (12.0, 10.0, 3.0, 3.0, 0.0)),)

    runner.instant.clear()
    revision = session.stats_revision
    first.style.visible = False
    assert runner.instant == []
    assert session.stats_revision == revision


def test_the_export_leaves_the_masks_out(tmp_path):
    controller, image = _controller_on_image(tmp_path)
    model = controller.analysis_model
    controller.viewer_model.browsed_directory = str(tmp_path)
    controller.viewer_model.paths = [image]
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    model.negative_mode = True
    model.canvas_roi_created = ("ellipse", [12.0, 10.0, 3.0, 3.0, 0.0])

    controller._write_export()

    (csv_path,) = (tmp_path / "analysis").glob("roi_intensities_*.csv")
    with open(csv_path, newline="", encoding="utf-8") as handle:
        records = list(csv.DictReader(handle))
    assert [record["roi"] for record in records] == ["ROI 1"]


def test_a_mask_and_its_paste_anchor_at_the_shown_image(tmp_path):
    controller, image = _controller_on_image(tmp_path)
    model = controller.analysis_model
    later = tmp_path / "a_2026_07_20-10_05_00_raw.png"
    later.write_bytes(b"")
    model.negative_mode = True
    model.canvas_roi_created = ("ellipse", [12.0, 10.0, 3.0, 3.0, 0.0])
    (mask,) = controller.session.rois

    assert mask.base_anchor == capture_timestamp(image)

    controller.viewer_model.current_path = str(later)
    model.selected_roi_id = mask.roi_id
    model.copy_roi_button = True
    model.paste_roi_button = True
    _mask, pasted = controller.session.rois

    assert pasted.base_anchor == capture_timestamp(str(later))


# ---------------------------------------------------------------------- #
# Undo / redo                                                             #
# ---------------------------------------------------------------------- #
def test_undoing_a_create_removes_it_and_redo_restores_the_same_roi():
    controller = _controller()
    model = controller.analysis_model
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    model.canvas_roi_created = ("ellipse", [40.0, 10.0, 5.0, 5.0, 0.0])
    first, second = controller.session.rois
    assert model.can_undo and not model.can_redo

    model.undo_roi_button = True
    assert controller.session.rois == [first]
    assert model.can_undo and model.can_redo

    model.redo_roi_button = True
    assert controller.session.rois[1] is second
    assert not model.can_redo


def test_undoing_an_edit_restores_geometry_and_overrides(tmp_path):
    controller, image = _controller_on_image(tmp_path)
    model = controller.analysis_model
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    (roi,) = controller.session.rois
    later = tmp_path / "a_2026_07_20-10_05_00_raw.png"
    later.write_bytes(b"")
    controller.viewer_model.current_path = str(later)
    model.canvas_roi_edited = (roi.roi_id, [12.0, 10.0, 5.0, 5.0, 0.0])
    model.canvas_roi_edited = (roi.roi_id, [14.0, 10.0, 5.0, 5.0, 0.0])
    anchor = capture_timestamp(str(later))
    assert roi.overrides == {anchor: [14.0, 10.0, 5.0, 5.0, 0.0]}

    model.undo_roi_button = True
    assert roi.overrides == {anchor: [12.0, 10.0, 5.0, 5.0, 0.0]}

    model.undo_roi_button = True
    assert roi.overrides == {}
    assert roi.geometry == [10.0, 10.0, 5.0, 5.0, 0.0]

    model.redo_roi_button = True
    assert roi.overrides == {anchor: [12.0, 10.0, 5.0, 5.0, 0.0]}


def test_undoing_a_delete_restores_the_roi_at_its_index():
    controller = _controller()
    model = controller.analysis_model

    for x in (10.0, 40.0, 70.0):
        model.canvas_roi_created = ("ellipse", [x, 10.0, 5.0, 5.0, 0.0])

    rois = list(controller.session.rois)
    model.selected_roi_id = rois[1].roi_id
    model.delete_roi_button = True
    assert controller.session.rois == [rois[0], rois[2]]

    model.undo_roi_button = True
    assert controller.session.rois == rois
    assert controller.session.rois[1] is rois[1]


def test_undoing_a_clear_restores_every_roi_in_order(monkeypatch):
    monkeypatch.setattr(roi_controller, "confirm", lambda **kwargs: YES)
    controller = _controller()
    model = controller.analysis_model

    for x in (10.0, 40.0, 70.0):
        model.canvas_roi_created = ("ellipse", [x, 10.0, 5.0, 5.0, 0.0])

    rois = list(controller.session.rois)
    model.clear_rois_button = True
    assert controller.session.rois == []
    assert model.undo_stack.undo_name == "Clear ROIs"

    model.undo_roi_button = True
    assert controller.session.rois == rois

    model.redo_roi_button = True
    assert controller.session.rois == []


def test_a_paste_is_one_undo_step():
    controller = _controller()
    model = controller.analysis_model
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    model.selected_roi_id = controller.session.rois[0].roi_id
    model.copy_roi_button = True
    model.paste_roi_button = True
    original, pasted = controller.session.rois

    model.undo_roi_button = True
    assert controller.session.rois == [original]

    model.redo_roi_button = True
    assert controller.session.rois[1] is pasted


def test_accepted_ai_rois_are_one_undo_step_with_distinct_names():
    controller = _controller()
    model = controller.analysis_model
    model.ai_rois_accepted = (
        [("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])] * 3,
        0.0,
    )
    names = [roi.name for roi in controller.session.rois]
    assert names == ["ROI 1", "ROI 2", "ROI 3"]
    assert len({roi.style.color for roi in controller.session.rois}) == 3

    model.undo_roi_button = True
    assert controller.session.rois == []
    assert not model.can_undo


def test_undo_flags_follow_the_stack():
    controller = _controller()
    model = controller.analysis_model
    assert not model.can_undo and not model.can_redo

    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    assert model.can_undo and not model.can_redo

    model.undo_roi_button = True
    assert not model.can_undo and model.can_redo

    # Nothing left to undo: a further press changes nothing.
    model.undo_roi_button = True
    assert controller.session.rois == []

    # A new change drops the redo branch.
    model.canvas_roi_created = ("box", [1.0, 1.0, 2.0, 2.0, 0.0])
    assert model.can_undo and not model.can_redo


def test_a_session_swap_empties_the_history(tmp_path):
    controller = _controller()
    model = controller.analysis_model
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    assert model.can_undo

    controller.viewer_model.browsed_directory = str(tmp_path)
    assert not model.can_undo and not model.can_redo
    assert model.undo_stack.undo_name == ""


def test_undoing_the_selected_rois_creation_clears_the_selection():
    controller = _controller()
    model = controller.analysis_model
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    model.selected_roi_id = controller.session.rois[0].roi_id

    model.undo_roi_button = True
    assert model.selected_roi_id == ""


def test_each_undo_and_redo_remeasures_the_positives_once(tmp_path):
    controller, image = _controller_on_image(tmp_path)
    model = controller.analysis_model
    session = controller.session
    runner = controller.runner
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    model.canvas_roi_created = ("ellipse", [40.0, 10.0, 5.0, 5.0, 0.0])
    model.negative_mode = True
    model.canvas_roi_created = ("ellipse", [12.0, 10.0, 3.0, 3.0, 0.0])
    positives = {roi.roi_id for roi in session.positive_rois}
    runner.instant.clear()
    revision = session.stats_revision

    model.undo_roi_button = True
    (undone,) = runner.instant
    assert undone[0] == image
    assert set(undone[1]) == positives, "one compute, positives only"
    assert undone[2][4] == ()
    assert session.stats_revision > revision

    runner.instant.clear()
    model.redo_roi_button = True
    (redone,) = runner.instant
    assert set(redone[1]) == positives
    assert redone[2][4] == (("ellipse", (12.0, 10.0, 3.0, 3.0, 0.0)),)


def test_deleting_on_one_image_keeps_the_roi_everywhere_else(tmp_path):
    controller, image = _controller_on_image(tmp_path)
    model = controller.analysis_model
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    (roi,) = controller.session.rois
    model.selected_roi_id = roi.roi_id

    model.delete_roi_button = True

    assert controller.session.rois == [roi]
    assert roi.absent_at == [capture_timestamp(image)]
    assert model.selected_roi_id == ""
    assert controller.viewer_model.absent_roi_count == 1

    model.undo_roi_button = True
    assert roi.absent_at == []
    assert controller.viewer_model.absent_roi_count == 0

    model.redo_roi_button = True
    model.restore_absent_rois_button = True
    assert roi.absent_at == []
    assert controller.viewer_model.absent_roi_count == 0


def _two_rois_on_image(tmp_path):
    """A controller on an image with two ROIs drawn on it."""
    controller, image = _controller_on_image(tmp_path)
    model = controller.analysis_model
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    model.canvas_roi_created = ("ellipse", [30.0, 30.0, 8.0, 8.0, 0.0])

    return controller, image


def test_renaming_a_redrawn_shape_makes_it_the_deleted_rois_shape_there(tmp_path):
    controller, image = _controller_on_image(tmp_path)
    model = controller.analysis_model
    runner = controller.runner
    capture_time = capture_timestamp(image)
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    (roi,) = controller.session.rois
    model.selected_roi_id = roi.roi_id
    model.delete_roi_button = True

    model.canvas_roi_created = ("ellipse", [30.0, 30.0, 8.0, 8.0, 0.0])
    _roi, replacement = controller.session.rois
    replacement.overrides = {capture_time + 60.0: [33.0, 30.0, 8.0, 8.0, 0.0]}
    model.selected_roi_id = replacement.roi_id
    runner.instant.clear()

    model.rename_roi_request = (replacement.roi_id, roi.name)

    assert controller.session.rois == [roi]
    assert roi.absent_at == []
    assert roi.effective_geometry(capture_time) == [30.0, 30.0, 8.0, 8.0, 0.0]
    # Tracking done on the merged ROI carries over.
    assert roi.effective_geometry(capture_time + 60.0) == [33.0, 30.0, 8.0, 8.0, 0.0]
    assert model.selected_roi_id == roi.roi_id
    assert model.progress_text == "ROI 2 merged into ROI 1"
    (remeasured,) = runner.instant
    assert remeasured[1] == {roi.roi_id: ("ellipse", (30.0, 30.0, 8.0, 8.0, 0.0))}

    model.undo_roi_button = True

    assert controller.session.rois == [roi, replacement]
    assert replacement.name == "ROI 2"
    assert roi.absent_at == [capture_time] and roi.local_overrides == {}


def test_a_name_collision_merges_whatever_the_shapes_history(tmp_path):
    controller, image = _two_rois_on_image(tmp_path)
    first, second = controller.session.rois

    # Not deleted from the image, and both drawn there: still a merge.
    controller.analysis_model.rename_roi_request = (second.roi_id, first.name)

    assert controller.session.rois == [first]
    assert first.effective_geometry(capture_timestamp(image)) == [
        30.0,
        30.0,
        8.0,
        8.0,
        0.0,
    ]


def test_recommitting_a_duplicate_name_merges_the_duplicates(tmp_path):
    controller, _image = _two_rois_on_image(tmp_path)
    first, second = controller.session.rois
    # Duplicates left by an earlier version's plain renames.
    second.name = first.name

    controller.analysis_model.rename_roi_request = (second.roi_id, second.name)

    assert controller.session.rois == [first]


def test_a_collision_without_an_image_or_with_a_mask_only_renames(tmp_path):
    controller = _controller()
    model = controller.analysis_model
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    model.canvas_roi_created = ("ellipse", [30.0, 30.0, 8.0, 8.0, 0.0])
    first, second = controller.session.rois

    model.rename_roi_request = (second.roi_id, first.name)

    assert controller.session.rois == [first, second]
    assert second.name == first.name
    assert model.progress_text == "Show an image to merge ROI 2 into ROI 1"

    masked, _image = _two_rois_on_image(tmp_path)
    masked.analysis_model.negative_mode = True
    masked.analysis_model.canvas_roi_created = ("ellipse", [9.0, 9.0, 2.0, 2.0, 0.0])
    roi, _other, mask = masked.session.rois

    masked.analysis_model.rename_roi_request = (mask.roi_id, roi.name)

    assert mask in masked.session.rois and mask.name == roi.name
    assert "Masks cannot be merged" in masked.analysis_model.progress_text


@pytest.mark.parametrize(
    "field, opened",
    [("absent_from", 1.0), ("absent_until", -1.0)],
    ids=["right", "left"],
)
def test_a_merge_opens_a_range_that_starts_or_ends_on_the_image(
    tmp_path, field, opened
):
    controller, image = _two_rois_on_image(tmp_path)
    first, second = controller.session.rois
    capture_time = capture_timestamp(image)
    # Both deleted over an inclusive range, as configs from before
    # Left / Right Del hold them: the merge keeps what both shared.
    setattr(first, field, capture_time)
    setattr(second, field, capture_time)

    controller.analysis_model.rename_roi_request = (second.roi_id, first.name)

    assert controller.session.rois == [first]
    assert first.applies_at(capture_time)
    # Every other image of the range stays deleted.
    assert not first.applies_at(capture_time + opened)


def test_a_merge_inside_a_range_asks_for_a_restore_first(tmp_path):
    controller, image = _two_rois_on_image(tmp_path)
    first, second = controller.session.rois
    first.absent_from = second.absent_from = capture_timestamp(image) - 60.0

    controller.analysis_model.rename_roi_request = (second.roi_id, first.name)

    assert controller.session.rois == [first, second]
    assert second.name == "ROI 2"
    assert "Restore it first" in controller.analysis_model.progress_text


def test_a_new_roi_is_never_named_after_an_existing_one():
    controller = _controller()
    model = controller.analysis_model

    for x in (10.0, 30.0, 50.0):
        model.canvas_roi_created = ("ellipse", [x, 10.0, 5.0, 5.0, 0.0])

    first, second, third = controller.session.rois
    second.name = first.name  # a duplicate, as plain renames could leave
    third.name = "Droplet"

    model.canvas_roi_created = ("ellipse", [70.0, 10.0, 5.0, 5.0, 0.0])
    names = [roi.name for roi in controller.session.rois]

    assert names[-1] not in names[:-1]


def test_a_drift_check_writes_nothing_over_a_correction_or_a_deletion():
    controller = _controller()
    model = controller.analysis_model
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    (roi,) = controller.session.rois
    roi.local_overrides = {200.0: [30.0, 30.0, 5.0, 5.0, 0.0]}
    roi.absent_at = [300.0]

    stray = Candidate(ellipse=[99.0, 99.0, 5.0, 5.0, 0.0])
    model.ai_roi_tracked = (roi.roi_id, 200.0, stray)
    model.ai_roi_tracked = (roi.roi_id, 300.0, stray)

    assert roi.local_overrides == {200.0: [30.0, 30.0, 5.0, 5.0, 0.0]}
    assert roi.overrides == {}

    model.ai_roi_tracked = (
        roi.roi_id,
        400.0,
        Candidate(ellipse=[50.0, 50.0, 5.0, 5.0, 0.0]),
    )

    assert roi.overrides == {400.0: [50.0, 50.0, 5.0, 5.0, 0.0]}


def test_a_tracked_shape_keeps_each_rois_own_kind():
    controller = _controller()
    model = controller.analysis_model
    drawn = [
        ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0]),
        ("polygon", [0.0, 0.0, 10.0, 0.0, 10.0, 10.0, 0.0, 10.0]),
        ("box", [0.0, 0.0, 20.0, 10.0, 0.0, 3.0]),
        ("capsule", [10.0, 10.0, 5.0, 3.0, 0.0]),
    ]

    for kind, geometry in drawn:
        model.canvas_roi_created = (kind, geometry)

    # A tracked droplet: its traced outline and fitted ellipse.
    candidate = Candidate(
        polygon=[40.0, 50.0, 60.0, 50.0, 60.0, 70.0, 40.0, 70.0],
        ellipse=[50.0, 60.0, 12.0, 8.0, 30.0],
    )

    for roi in controller.session.rois:
        model.ai_roi_tracked = (roi.roi_id, 400.0, candidate)

    ellipse, polygon, box, capsule = (
        roi.overrides[400.0] for roi in controller.session.rois
    )
    ellipse_area = math.pi * 12.0 * 8.0

    assert ellipse == [50.0, 60.0, 12.0, 8.0, 30.0]
    assert polygon == list(candidate.polygon)

    # Same centre, tilt and proportions; the drawn corner radius kept;
    # what the rounded box encloses matches the ellipse.
    x, y, width, height, angle, corner_radius = box
    assert (x + width / 2.0, y + height / 2.0) == pytest.approx((50.0, 60.0))
    assert (angle, corner_radius) == (30.0, 3.0)
    assert width / height == pytest.approx(1.5)
    assert width * height - (4.0 - math.pi) * 3.0**2 == pytest.approx(ellipse_area)

    cx, cy, half_length, radius, angle = capsule
    assert (cx, cy, angle) == (50.0, 60.0, 30.0)
    assert (half_length + radius) / radius == pytest.approx(1.5)
    assert 4.0 * half_length * radius + math.pi * radius**2 == pytest.approx(
        ellipse_area
    )


@pytest.mark.parametrize("rename_old_onto_new", [False, True])
def test_a_merge_keeps_the_longer_lived_roi_whichever_way_it_is_renamed(
    tmp_path, rename_old_onto_new
):
    controller, image = _controller_on_image(tmp_path)
    model = controller.analysis_model
    capture_time = capture_timestamp(image)
    # The long-standing ROI: drawn before the shown image, tracked since.
    old = Roi(
        name="ROI 1",
        kind="ellipse",
        geometry=[10.0, 10.0, 5.0, 5.0, 0.0],
        base_anchor=capture_time - 120.0,
        overrides={capture_time - 60.0: [12.0, 10.0, 5.0, 5.0, 0.0]},
        absent_at=[capture_time],
        expected_fastest_change=42.0,
    )
    controller.session.rois.append(old)
    model.canvas_roi_created = ("ellipse", [30.0, 30.0, 8.0, 8.0, 0.0])
    new = controller.session.rois[-1]
    renamed, target = (old, new) if rename_old_onto_new else (new, old)
    typed = target.name
    model.selected_roi_id = renamed.roi_id

    model.rename_roi_request = (renamed.roi_id, typed)

    # The old ROI survives, whatever the direction, under the typed name,
    # with its own definitions everywhere but the shown image.
    assert controller.session.rois == [old]
    assert old.name == typed
    assert old.geometry == [10.0, 10.0, 5.0, 5.0, 0.0]
    assert old.effective_geometry(capture_time - 60.0) == [12.0, 10.0, 5.0, 5.0, 0.0]
    assert old.effective_geometry(capture_time) == [30.0, 30.0, 8.0, 8.0, 0.0]
    assert old.absent_at == [] and old.expected_fastest_change == 42.0
    assert model.selected_roi_id == old.roi_id
    assert model.progress_text == f"{new.name} merged into {typed}"

    model.undo_roi_button = True

    assert controller.session.rois == [old, new]
    assert old.name == "ROI 1" and new.name == "ROI 2"
    assert old.absent_at == [capture_time] and old.local_overrides == {}


@pytest.mark.parametrize(
    "button, before, after",
    [("delete_roi_right_button", True, False), ("delete_roi_left_button", False, True)],
)
def test_deleting_over_a_range_spares_the_shown_image_and_the_rest(
    tmp_path, button, before, after
):
    controller, image = _controller_on_image(tmp_path)
    model = controller.analysis_model
    capture_time = capture_timestamp(image)
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    (roi,) = controller.session.rois
    model.selected_roi_id = roi.roi_id

    setattr(model, button, True)

    assert controller.session.rois == [roi]
    assert roi.applies_at(capture_time - 60.0) is before
    assert roi.applies_at(capture_time)
    assert roi.applies_at(capture_time + 60.0) is after
    assert controller.viewer_model.absent_roi_count == 0

    # Restore from an image the ROI is off, as a range restore: it
    # clears the range that covers that image.
    off_image_time = "10_01_00" if after is False else "09_59_00"
    restore_on = tmp_path / f"b_2026_07_20-{off_image_time}_raw.png"
    restore_on.write_bytes(b"")
    controller.viewer_model.current_path = str(restore_on)

    assert controller.viewer_model.absent_roi_count == 1
    assert controller.viewer_model.absent_roi_ranged
    assert "ranges" in controller.viewer_model.absent_roi_text

    model.restore_absent_rois_button = True

    assert roi.applies_at(capture_timestamp(str(restore_on)))
    assert controller.viewer_model.absent_roi_count == 0

    model.undo_roi_button = True

    assert not roi.applies_at(capture_timestamp(str(restore_on)))


def test_hiding_the_selected_roi_clears_the_selection():
    controller = _controller()
    model = controller.analysis_model
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    model.canvas_roi_created = ("ellipse", [30.0, 10.0, 5.0, 5.0, 0.0])
    first, second = controller.session.rois
    model.selected_roi_id = first.roi_id

    second.style.visible = False
    assert model.selected_roi_id == first.roi_id

    first.style.visible = False
    assert model.selected_roi_id == ""


def test_switching_eyes_on_orders_the_rois_last_shown_last():
    controller = _controller()
    model = controller.analysis_model
    session = controller.session
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    model.canvas_roi_created = ("ellipse", [30.0, 10.0, 5.0, 5.0, 0.0])
    first, second = session.rois
    assert session.visibility_order == []

    second.style.visible = False
    first.style.visible = False
    second.style.visible = True
    first.style.visible = True
    assert session.visibility_order == [second.roi_id, first.roi_id]

    second.style.visible = False
    assert session.visibility_order == [first.roi_id]

    second.style.visible = True
    assert session.visibility_order == [first.roi_id, second.roi_id]
