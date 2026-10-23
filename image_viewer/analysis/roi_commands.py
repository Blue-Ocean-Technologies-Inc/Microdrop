# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Undoable changes to an analysis session's drawn shapes, for the pyface
CommandStack the ROI analysis model holds.

The commands hold the session and the Roi objects, never the
``session.rois`` list itself: that container is replaced wholesale (a
clear, a load), and a command still holding the old one would edit a list
nobody looks at (#755). Each list change resolves ``session.rois`` live
and lands as one list change, so a multi-ROI step notifies once."""

# Enthought library imports.
from pyface.undo.api import AbstractCommand
from traits.api import Any, Bool, Float, Instance, Int, List, Str, Tuple

# Local imports.
from .roi_model import AnalysisSession, Roi


def _contains(rois, roi):
    """Whether ``roi`` is one of ``rois`` — by identity, as two ROIs may
    compare equal in every trait."""
    return any(member is roi for member in rois)


def _remove_from_session(session, rois):
    """Take ``rois`` out of the session's live list; return the
    ``(index, roi)`` pairs they held, ascending."""
    live = list(session.rois)
    pairs = [(index, roi) for index, roi in enumerate(live) if _contains(rois, roi)]
    session.rois[:] = [roi for roi in live if not _contains(rois, roi)]

    return pairs


def _insert_into_session(session, pairs):
    """Put each ``(index, roi)`` back where it was. Inserting in
    ascending index order rebuilds the original order exactly."""
    rois = list(session.rois)

    for index, roi in sorted(pairs, key=lambda pair: pair[0]):
        rois.insert(min(index, len(rois)), roi)

    session.rois[:] = rois


def _copied(overrides):
    """A deep copy of an {anchor: geometry} dict, so a snapshot shares
    no list with the ROI it was taken from."""
    return {anchor: list(geometry) for anchor, geometry in overrides.items()}


class _SessionCommand(AbstractCommand):
    """A change to one session's ROI set."""

    #: The session the change applies to. The ROI list is read from it
    #: at do/undo/redo time, never kept.
    session = Instance(AnalysisSession)


class AddRoisCommand(_SessionCommand):
    """Add one or more ROIs as one step — a drawn or pasted shape, or a
    set of accepted AI candidates."""

    #: The ROIs added, in the order they are appended.
    rois = List(Instance(Roi))

    #: Where each ROI stood when last undone, so a redo puts it back
    #: there rather than at the end.
    _pairs = List(Tuple(Int, Instance(Roi)))

    def _name_default(self):
        if len(self.rois) == 1:
            return f"Add {self.rois[0].name}"

        return f"Add {len(self.rois)} ROIs"

    def do(self):
        start = len(self.session.rois)
        self._pairs = [(start + offset, roi) for offset, roi in enumerate(self.rois)]
        self.redo()

    def undo(self):
        self._pairs = _remove_from_session(self.session, self.rois)

    def redo(self):
        _insert_into_session(self.session, self._pairs)


class RemoveRoisCommand(_SessionCommand):
    """Remove ROIs as one step — a delete, or clearing the lot."""

    #: The ROIs removed.
    rois = List(Instance(Roi))

    #: Where each removed ROI stood, ascending, for the undo.
    _pairs = List(Tuple(Int, Instance(Roi)))

    def _name_default(self):
        if len(self.rois) == 1:
            return f"Delete {self.rois[0].name}"

        return "Clear ROIs"

    def do(self):
        self.redo()

    def undo(self):
        _insert_into_session(self.session, self._pairs)

    def redo(self):
        self._pairs = _remove_from_session(self.session, self.rois)


class EditRoiCommand(_SessionCommand):
    """One committed canvas gesture on an ROI (move, resize, rotate, a
    corner or vertex drag), recorded through ``Roi.apply_edit``. Each
    gesture is its own step: edits never merge."""

    #: The edited ROI.
    roi = Instance(Roi)

    #: Capture time of the image the edit was made on (see apply_edit).
    capture_time = Float()

    #: The geometry the gesture left the shape with.
    geometry = List(Float)

    #: The ROI's base geometry, overrides and single-image overrides
    #: before the edit.
    _before = Tuple(List, Any, Any)

    def _name_default(self):
        return f"Edit {self.roi.name}"

    def do(self):
        self._before = (
            list(self.roi.geometry),
            _copied(self.roi.overrides),
            _copied(self.roi.local_overrides),
        )
        self.redo()

    def undo(self):
        # Fresh list and dict objects: the canvas follows ``geometry``,
        # ``overrides.items`` and ``local_overrides`` by assignment.
        geometry, overrides, local_overrides = self._before
        self.roi.geometry = list(geometry)
        self.roi.overrides = _copied(overrides)
        self.roi.local_overrides = _copied(local_overrides)

    def redo(self):
        self.roi.apply_edit(self.capture_time, list(self.geometry))


class HideRoiOnImageCommand(_SessionCommand):
    """Delete an ROI from one image only (its ``absent_at``), leaving
    every other image as it was — or, with ``restore``, put it back on
    that image."""

    #: The ROI taken off (or put back on) the image.
    roi = Instance(Roi)

    #: Capture time of the image.
    capture_time = Float()

    #: Put the ROI back on the image instead of taking it off.
    restore = Bool(False)

    def _name_default(self):
        verb = "Restore" if self.restore else "Delete"

        return f"{verb} {self.roi.name} on one image"

    def do(self):
        self.redo()

    def undo(self):
        self._set_absent(self.restore)

    def redo(self):
        self._set_absent(not self.restore)

    def _set_absent(self, absent):
        times = [time for time in self.roi.absent_at if time != self.capture_time]

        # A fresh list: the canvas and the table follow it by assignment.
        self.roi.absent_at = sorted([*times, self.capture_time]) if absent else times


class MergeRoiOnImageCommand(_SessionCommand):
    """Give ``roi`` the shape ``replacement`` has on one image, there
    alone, and drop ``replacement`` — a shape redrawn on an image taking
    over the identity (id, plot line, CSV column, style) of the ROI that
    was deleted from that image."""

    #: The ROI keeping its identity: back on the image, in a new shape.
    roi = Instance(Roi)

    #: The ROI whose shape it takes there, removed from the session.
    replacement = Instance(Roi)

    #: Capture time of the image.
    capture_time = Float()

    #: The replacement's name before the rename that asked for the
    #: merge, given back to it on undo.
    replacement_name = Str()

    #: ``roi``'s single-image shapes and absences before the merge.
    _before = Tuple(Any, List)

    #: Where the replacement stood in the ROI list, for the undo.
    _pairs = List(Tuple(Int, Instance(Roi)))

    def _name_default(self):
        return f"Replace {self.roi.name} on one image"

    def do(self):
        self._before = (_copied(self.roi.local_overrides), list(self.roi.absent_at))
        self.redo()

    def undo(self):
        local_overrides, absent_at = self._before
        self.roi.local_overrides = _copied(local_overrides)
        self.roi.absent_at = list(absent_at)
        _insert_into_session(self.session, self._pairs)

        if self.replacement_name:
            self.replacement.name = self.replacement_name

    def redo(self):
        capture_time = self.capture_time
        self.roi.local_overrides = {
            **_copied(self.roi.local_overrides),
            capture_time: self.replacement.effective_geometry(capture_time),
        }
        self.roi.absent_at = [
            time for time in self.roi.absent_at if time != capture_time
        ]
        self._pairs = _remove_from_session(self.session, [self.replacement])
