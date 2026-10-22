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

# Enthought library imports.
from pyface.api import YES

# Microdrop package imports.
from image_viewer.analysis import roi_controller
from image_viewer.analysis.consts import (
    DEFAULT_ROI_COLORS,
    DELETE_ROI_ALL_IMAGES,
    DELETE_ROI_THIS_IMAGE,
    NEGATIVE_MASK_COLOR,
    PASTE_OFFSET_PX,
)
from image_viewer.analysis.roi_batch import (
    RoiBatchRunner,
)
from image_viewer.analysis.roi_controller import (
    RoiAnalysisController,
)
from image_viewer.analysis.roi_model import (
    RoiAnalysisModel,
)
from image_viewer.discovery import capture_timestamp
from image_viewer.model import (
    ImageViewerModel,
)


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


def test_delete_removes_the_selected_roi_and_says_so_when_there_is_none():
    controller = _controller()
    model = controller.analysis_model
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    model.selected_roi_id = controller.session.rois[0].roi_id

    model.delete_roi_button = True
    assert controller.session.rois == []
    assert model.selected_roi_id == ""

    model.delete_roi_button = True
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
    controller = RoiAnalysisController(
        viewer_model=ImageViewerModel(),
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


def test_changing_a_mask_remeasures_every_roi_on_the_image(tmp_path, monkeypatch):
    monkeypatch.setattr(
        roi_controller, "choose", lambda **kwargs: DELETE_ROI_ALL_IMAGES
    )
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


def test_deleting_on_one_image_keeps_the_roi_everywhere_else(tmp_path, monkeypatch):
    monkeypatch.setattr(
        roi_controller, "choose", lambda **kwargs: DELETE_ROI_THIS_IMAGE
    )
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


def test_cancelling_the_delete_dialog_deletes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(roi_controller, "choose", lambda **kwargs: None)
    controller, _image = _controller_on_image(tmp_path)
    model = controller.analysis_model
    model.canvas_roi_created = ("ellipse", [10.0, 10.0, 5.0, 5.0, 0.0])
    (roi,) = controller.session.rois
    model.selected_roi_id = roi.roi_id

    model.delete_roi_button = True

    assert controller.session.rois == [roi] and roi.absent_at == []
