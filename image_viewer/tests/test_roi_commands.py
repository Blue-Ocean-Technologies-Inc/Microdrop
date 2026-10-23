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

# Enthought library imports.
from pyface.undo.api import CommandStack, UndoManager

# Microdrop package imports.
from image_viewer.analysis.roi_commands import (
    AddRoisCommand,
    EditRoiCommand,
    HideRoiOnImageCommand,
    MergeRoiOnImageCommand,
    RemoveRoisCommand,
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
    assert stack.undo_name == "Delete ROI 1 on one image"

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
    assert stack.undo_name == "Restore ROI 1 on one image"

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


def test_merging_a_redrawn_shape_into_an_roi_on_one_image_undoes_and_redoes():
    session = _session(2)
    roi, replacement = session.rois
    roi.absent_at = [100.0, 300.0]
    replacement.name = roi.name
    stack = _stack()

    stack.push(
        MergeRoiOnImageCommand(
            session=session,
            roi=roi,
            replacement=replacement,
            capture_time=100.0,
            replacement_name="ROI 2",
        )
    )
    assert session.rois == [roi]
    assert roi.local_overrides == {100.0: [2.0] * 5}
    assert roi.absent_at == [300.0]
    assert stack.undo_name == "Replace ROI 1 on one image"

    stack.undo()
    assert session.rois == [roi, replacement]
    assert roi.local_overrides == {} and roi.absent_at == [100.0, 300.0]
    assert replacement.name == "ROI 2"

    stack.redo()
    assert session.rois == [roi]
    assert roi.effective_geometry(100.0) == [2.0] * 5
