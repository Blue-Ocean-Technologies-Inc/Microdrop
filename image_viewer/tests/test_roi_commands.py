# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The undoable ROI shape commands on their own, against a pyface
CommandStack — including the #755 rule that they follow the session's
live ROI list rather than the list object they first saw."""

# Standard library imports.
import math

# Enthought library imports.
from pyface.undo.api import CommandStack, UndoManager

# Microdrop package imports.
from image_viewer.analysis.roi_commands import (
    AddRoisCommand,
    EditRoiCommand,
    HideRoiOnImageCommand,
    MergeRoiOnImageCommand,
    RemoveRoisCommand,
    merged_absences,
)
from image_viewer.analysis.roi_model import AnalysisSession, Roi


def _stack():
    manager = UndoManager()
    stack = CommandStack(undo_manager=manager)
    manager.active_stack = stack

    return stack


def _session(count):
    return AnalysisSession(
        rois=[
            Roi(name=f"ROI {number}", kind="ellipse", geometry=[float(number)] * 5)
            for number in range(1, count + 1)
        ]
    )


def _ids(session):
    return [roi.roi_id for roi in session.rois]


def test_add_undo_redo_puts_the_same_roi_back_in_place():
    session = _session(2)
    stack = _stack()
    added = Roi(name="ROI 3", kind="box", geometry=[1.0, 2.0, 3.0, 4.0, 0.0])

    stack.push(AddRoisCommand(session=session, rois=[added]))
    assert session.rois[-1] is added
    assert stack.undo_name == "Add ROI 3"

    stack.undo()
    assert not any(roi is added for roi in session.rois)
    assert stack.redo_name == "Add ROI 3"

    stack.redo()
    assert session.rois[2] is added
    assert len(session.rois) == 3


def test_a_grouped_add_is_one_step():
    session = _session(1)
    stack = _stack()
    group = [Roi(name=f"ROI {number}", kind="ellipse") for number in (2, 3, 4)]

    stack.push(AddRoisCommand(session=session, rois=group))
    assert stack.undo_name == "Add 3 ROIs"
    assert len(session.rois) == 4

    stack.undo()
    assert len(session.rois) == 1
    assert stack.undo_name == ""

    stack.redo()
    assert session.rois[1:] == group


def test_remove_undo_reinserts_at_the_original_indices():
    session = _session(5)
    before = _ids(session)
    stack = _stack()
    removed = [session.rois[1], session.rois[3]]

    stack.push(RemoveRoisCommand(session=session, rois=removed))
    assert _ids(session) == [before[0], before[2], before[4]]

    stack.undo()
    assert _ids(session) == before
    assert session.rois[1] is removed[0] and session.rois[3] is removed[1]

    stack.redo()
    assert _ids(session) == [before[0], before[2], before[4]]


def test_remove_names_a_single_delete_and_a_clear():
    session = _session(2)
    single = RemoveRoisCommand(session=session, rois=[session.rois[0]])
    clear = RemoveRoisCommand(
        session=session, rois=list(session.rois), name="Clear ROIs"
    )

    assert single.name == "Delete ROI 1"
    assert clear.name == "Clear ROIs"


def test_edit_undo_restores_geometry_and_overrides_exactly():
    session = _session(1)
    (roi,) = session.rois
    roi.base_anchor = 10.0
    roi.overrides = {20.0: [9.0, 9.0, 9.0, 9.0, 0.0]}
    geometry = list(roi.geometry)
    stack = _stack()

    stack.push(
        EditRoiCommand(
            session=session,
            roi=roi,
            capture_time=30.0,
            geometry=[5.0, 6.0, 7.0, 8.0, 0.0],
        )
    )
    assert roi.overrides[30.0] == [5.0, 6.0, 7.0, 8.0, 0.0]
    assert stack.undo_name == "Edit ROI 1"

    stack.undo()
    assert roi.geometry == geometry
    assert dict(roi.overrides) == {20.0: [9.0, 9.0, 9.0, 9.0, 0.0]}

    stack.redo()
    assert roi.overrides[30.0] == [5.0, 6.0, 7.0, 8.0, 0.0]


def test_edits_never_merge():
    session = _session(1)
    (roi,) = session.rois
    stack = _stack()

    for x in (2.0, 3.0):
        stack.push(
            EditRoiCommand(
                session=session,
                roi=roi,
                capture_time=0.0,
                geometry=[x, 1.0, 1.0, 1.0, 0.0],
            )
        )

    stack.undo()
    assert roi.geometry[0] == 2.0

    stack.undo()
    assert roi.geometry[0] == 1.0


def test_commands_follow_the_live_list_after_it_is_replaced():
    # The #755 trap: a load or clear replaces session.rois, and a
    # command that kept the old list object would edit a dead copy.
    session = _session(2)
    stack = _stack()
    added = Roi(name="ROI 3", kind="ellipse")
    stack.push(AddRoisCommand(session=session, rois=[added]))
    session.rois = list(session.rois)

    stack.undo()
    assert len(session.rois) == 2
    session.rois = list(session.rois)

    stack.redo()
    assert session.rois[-1] is added

    removed = session.rois[0]
    stack.push(RemoveRoisCommand(session=session, rois=[removed]))
    session.rois = list(session.rois)

    stack.undo()
    assert session.rois[0] is removed


def test_hiding_an_roi_on_one_image_undoes_and_redoes():
    session = _session(1)
    (roi,) = session.rois
    roi.absent_at = [300.0]
    stack = _stack()

    stack.push(HideRoiOnImageCommand(session=session, roi=roi, capture_time=100.0))
    assert roi.absent_at == [100.0, 300.0]
    assert stack.undo_name == "Delete ROI 1 on this image"

    stack.undo()
    assert roi.absent_at == [300.0]

    stack.redo()
    assert roi.absent_at == [100.0, 300.0]
    assert session.rois == [roi]  # still in every other image


def test_restoring_an_roi_on_one_image_is_the_inverse():
    session = _session(1)
    (roi,) = session.rois
    roi.absent_at = [100.0]
    stack = _stack()

    stack.push(
        HideRoiOnImageCommand(
            session=session, roi=roi, capture_time=100.0, restore=True
        )
    )
    assert roi.absent_at == []
    assert stack.undo_name == "Restore ROI 1 on this image"

    stack.undo()
    assert roi.absent_at == [100.0]


def test_edit_undo_restores_a_single_image_shape():
    session = _session(1)
    (roi,) = session.rois
    roi.local_overrides = {30.0: [1.0, 1.0, 1.0, 1.0, 0.0]}
    stack = _stack()

    stack.push(
        EditRoiCommand(
            session=session,
            roi=roi,
            capture_time=30.0,
            geometry=[5.0, 6.0, 7.0, 8.0, 0.0],
        )
    )
    assert roi.local_overrides == {30.0: [5.0, 6.0, 7.0, 8.0, 0.0]}
    assert roi.overrides == {}

    stack.undo()
    assert roi.local_overrides == {30.0: [1.0, 1.0, 1.0, 1.0, 0.0]}


def test_a_merge_takes_each_images_shape_from_whichever_roi_defined_it():
    session = _session(2)
    history, correction = session.rois
    history.geometry = [1.0] * 5
    history.overrides = {
        100.0: [10.0] * 5,
        260.0: [26.0] * 5,  # inside the correction's span: it goes
        400.0: [40.0] * 5,  # after it: it takes over again
    }
    history.local_overrides = {50.0: [5.0] * 5}
    correction.trait_set(
        geometry=[20.0] * 5,
        base_anchor=200.0,
        overrides={300.0: [30.0] * 5},
        local_overrides={350.0: [35.0] * 5},
    )
    stack = _stack()

    stack.push(
        MergeRoiOnImageCommand(
            session=session,
            roi=history,
            replacement=correction,
            capture_time=250.0,
            merged_name="Droplet",
        )
    )

    assert session.rois == [history]
    assert history.name == "Droplet"
    assert stack.undo_name == "Merge ROI 2 into Droplet"
    shapes = {
        time: history.effective_geometry(time)[0]
        for time in (0.0, 50.0, 150.0, 200.0, 250.0, 270.0, 300.0, 350.0, 400.0, 500.0)
    }
    assert shapes == {
        0.0: 1.0,  # history's base
        50.0: 5.0,  # history's single-image shape
        150.0: 10.0,  # history's override, before the correction's span
        200.0: 20.0,  # the correction's base, from its anchor
        250.0: 20.0,  # the shown image: the correction's shape
        270.0: 20.0,  # the history's anchor inside the span is gone
        300.0: 30.0,  # the correction's override
        350.0: 35.0,  # the correction's single-image shape
        400.0: 40.0,  # the history's later override takes over again
        500.0: 40.0,
    }

    stack.undo()

    assert session.rois == [history, correction]
    assert history.name == "ROI 1"
    assert history.overrides == {
        100.0: [10.0] * 5,
        260.0: [26.0] * 5,
        400.0: [40.0] * 5,
    }
    assert history.local_overrides == {50.0: [5.0] * 5}

    stack.redo()
    assert history.effective_geometry(270.0) == [20.0] * 5


def test_right_and_left_del_spare_the_shown_image():
    session = _session(1)
    (roi,) = session.rois
    stack = _stack()

    stack.push(
        HideRoiOnImageCommand(
            session=session, roi=roi, capture_time=200.0, scope="right"
        )
    )
    assert stack.undo_name == "Delete ROI 1 on later images"
    assert roi.applies_at(100.0) and roi.applies_at(200.0)
    assert not roi.applies_at(200.001) and not roi.applies_at(1e9)
    assert roi.absent_by(300.0) == ["right"] and roi.absent_by(200.0) == []

    stack.undo()
    stack.push(
        HideRoiOnImageCommand(
            session=session, roi=roi, capture_time=200.0, scope="left"
        )
    )
    assert stack.undo_name == "Delete ROI 1 on earlier images"
    assert roi.applies_at(200.0) and roi.applies_at(300.0)
    assert not roi.applies_at(199.999) and not roi.applies_at(0.0)
    assert roi.absent_by(100.0) == ["left"] and roi.absent_by(200.0) == []


def test_deleting_right_widens_and_left_extends_the_range():
    session = _session(1)
    (roi,) = session.rois
    stack = _stack()

    stack.push(
        HideRoiOnImageCommand(
            session=session, roi=roi, capture_time=200.0, scope="right"
        )
    )
    stack.push(
        HideRoiOnImageCommand(
            session=session, roi=roi, capture_time=300.0, scope="right"
        )
    )
    # The earliest start wins, just past its image.
    assert roi.absent_from == math.nextafter(200.0, math.inf)

    stack.push(
        HideRoiOnImageCommand(
            session=session, roi=roi, capture_time=100.0, scope="left"
        )
    )
    stack.push(
        HideRoiOnImageCommand(session=session, roi=roi, capture_time=50.0, scope="left")
    )
    # The latest end wins, just short of its image.
    assert roi.absent_until == math.nextafter(100.0, -math.inf)
    assert stack.undo_name == "Delete ROI 1 on earlier images"

    stack.undo()
    stack.undo()
    assert math.isnan(roi.absent_until)
    assert roi.absent_from == math.nextafter(200.0, math.inf)


def test_restoring_a_range_clears_it_and_undo_brings_it_back():
    session = _session(1)
    (roi,) = session.rois
    roi.absent_from = 200.0
    stack = _stack()

    stack.push(
        HideRoiOnImageCommand(
            session=session,
            roi=roi,
            capture_time=250.0,
            scope="right",
            restore=True,
        )
    )
    assert math.isnan(roi.absent_from)
    assert stack.undo_name == "Restore ROI 1 on later images"

    stack.undo()
    assert roi.absent_from == 200.0


def test_a_merged_roi_is_absent_only_where_both_were():
    history = Roi(absent_at=[10.0, 20.0, 30.0], absent_from=500.0, absent_until=5.0)
    correction = Roi(absent_at=[20.0, 600.0], absent_from=550.0, absent_until=50.0)

    # 10 and 30 the correction's left range covers, 600 the history's
    # right one; the ranges keep their overlap.
    assert merged_absences(history, correction, 100.0) == (
        [10.0, 20.0, 30.0, 600.0],
        550.0,
        5.0,
    )


def test_a_merge_shows_the_roi_where_the_ranges_cannot_say_both():
    # The history's "right" crossed with the correction's "left" is a
    # bounded stretch: shown rather than lost.
    history = Roi(absent_from=100.0)
    correction = Roi(absent_until=200.0)

    absent_at, absent_from, absent_until = merged_absences(history, correction, 300.0)

    assert absent_at == []
    assert math.isnan(absent_from) and math.isnan(absent_until)


def test_a_merge_keeps_a_left_and_a_right_range_both_had():
    # Right Del and Left Del from the shown image, on both ROIs: the
    # ranges already stop short of it, so the merge keeps them as they are.
    shown = 200.0
    ranges = {
        "absent_from": math.nextafter(shown, math.inf),
        "absent_until": math.nextafter(shown, -math.inf),
    }
    history = Roi(**ranges)
    correction = Roi(**ranges)

    absent_at, absent_from, absent_until = merged_absences(history, correction, shown)

    assert absent_at == []
    assert (absent_from, absent_until) == (
        ranges["absent_from"],
        ranges["absent_until"],
    )
    merged = Roi(absent_from=absent_from, absent_until=absent_until)
    assert merged.applies_at(shown)
    assert not merged.applies_at(100.0) and not merged.applies_at(300.0)


def test_a_merge_opens_a_shared_range_at_the_shown_image_or_refuses():
    history = Roi(absent_from=100.0)
    correction = Roi(absent_from=100.0)

    _at, absent_from, _until = merged_absences(history, correction, 100.0)

    assert 100.0 < absent_from < 100.0 + 1e-9
    assert merged_absences(history, correction, 150.0) is None


def test_undoing_a_merge_gives_back_both_rois_whole():
    session = _session(2)
    survivor, removed = session.rois
    removed.trait_set(
        overrides={200.0: [22.0] * 5},
        local_overrides={300.0: [33.0] * 5},
        absent_at=[400.0],
        absent_until=50.0,
        expected_fastest_change=12.0,
        is_background_ref=True,
    )
    removed.style.color = "#123456"
    stack = _stack()

    stack.push(
        MergeRoiOnImageCommand(
            session=session,
            roi=survivor,
            replacement=removed,
            capture_time=100.0,
            merged_name="Droplet",
        )
    )
    assert survivor.name == "Droplet"

    stack.undo()

    assert session.rois == [survivor, removed]
    assert survivor.name == "ROI 1"
    assert removed.name == "ROI 2"
    assert removed.overrides == {200.0: [22.0] * 5}
    assert removed.local_overrides == {300.0: [33.0] * 5}
    assert removed.absent_at == [400.0] and removed.absent_until == 50.0
    assert removed.expected_fastest_change == 12.0 and removed.is_background_ref
    assert removed.style.color == "#123456"


def test_left_and_right_del_from_one_image_keep_it_there_alone():
    session = _session(1)
    (roi,) = session.rois
    stack = _stack()

    for scope in ("left", "right"):
        stack.push(
            HideRoiOnImageCommand(
                session=session, roi=roi, capture_time=200.0, scope=scope
            )
        )

    assert roi.applies_at(200.0)
    assert not roi.applies_at(100.0) and not roi.applies_at(300.0)

    stack.undo()
    assert roi.applies_at(300.0) and not roi.applies_at(100.0)

    stack.redo()
    stack.push(
        HideRoiOnImageCommand(
            session=session,
            roi=roi,
            capture_time=300.0,
            scope="right",
            restore=True,
        )
    )
    assert roi.applies_at(300.0) and not roi.applies_at(100.0)
