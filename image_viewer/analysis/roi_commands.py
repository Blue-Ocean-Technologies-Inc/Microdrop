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

# Standard library imports.
import math

# Enthought library imports.
from pyface.undo.api import AbstractCommand
from traits.api import Any, Bool, Enum, Float, Instance, Int, List, Str, Tuple

# Local imports.
from .consts import ROI_ABSENCE_SCOPES
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


#: The undo stack's wording of each HideRoiOnImageCommand scope.
_ABSENCE_SCOPE_WORDS = {
    "image": "on one image",
    "later": "from one image on",
    "earlier": "up to one image",
    "except": "everywhere but one image",
}


class HideRoiOnImageCommand(_SessionCommand):
    """Delete an ROI from one image and, by ``scope``, every later or
    every earlier one too, leaving the others as they were — or, with
    ``restore``, undo such a deletion: put it back on that image, or
    clear the range."""

    #: The ROI taken off (or put back on) the images.
    roi = Instance(Roi)

    #: Capture time of the image.
    capture_time = Float()

    #: That image alone (absent_at), it and every later one
    #: (absent_from), it and every earlier one (absent_until), or every
    #: image but it (both ranges, stopping either side of it).
    #: Repeating "later" from another image widens the range — the
    #: earliest start wins — and "earlier" likewise keeps the latest end.
    scope = Enum(*ROI_ABSENCE_SCOPES)

    #: Undo that deletion instead of making it.
    restore = Bool(False)

    #: The ROI's absences before the step: (absent_at, absent_from,
    #: absent_until).
    _before = Tuple(List, Float, Float)

    def _name_default(self):
        verb = "Restore" if self.restore else "Delete"

        return f"{verb} {self.roi.name} {_ABSENCE_SCOPE_WORDS[self.scope]}"

    def do(self):
        roi = self.roi
        self._before = (list(roi.absent_at), roi.absent_from, roi.absent_until)
        self.redo()

    def undo(self):
        absent_at, absent_from, absent_until = self._before
        # A fresh list: the canvas and the table follow it by assignment.
        self.roi.trait_set(
            absent_at=list(absent_at),
            absent_from=absent_from,
            absent_until=absent_until,
        )

    def redo(self):
        roi, capture_time = self.roi, self.capture_time

        if self.scope == "except":
            # Ranges stopping either side of the image, so captures still
            # to come are covered too.
            roi.trait_set(
                absent_until=(
                    math.nan
                    if self.restore
                    else math.nextafter(capture_time, -math.inf)
                ),
                absent_from=(
                    math.nan if self.restore else math.nextafter(capture_time, math.inf)
                ),
            )
        elif self.scope == "later":
            roi.absent_from = (
                math.nan if self.restore else _bound(min, roi.absent_from, capture_time)
            )
        elif self.scope == "earlier":
            roi.absent_until = (
                math.nan
                if self.restore
                else _bound(max, roi.absent_until, capture_time)
            )
        else:
            times = [time for time in roi.absent_at if time != capture_time]
            roi.absent_at = times if self.restore else sorted([*times, capture_time])


def _bound(pick, current, capture_time):
    """``capture_time``, or ``pick`` of it and ``current`` when a range
    is already set (``current`` not NaN)."""
    return capture_time if math.isnan(current) else pick(current, capture_time)


def merged_overrides(history, correction, capture_time):
    """``history``'s forward overrides with ``correction``'s definitions
    laid over them, so the merged shape on each image is the
    correction's wherever it defined one and the history's elsewhere.

    The correction's definitions are its forward overrides plus its base
    geometry from its base anchor (unless that is the shown image, where
    the merge gives it as the single-image shape instead). Between its
    first and last anchor the correction holds, so the history's anchors
    in there go; past its last anchor any later history anchor takes
    over again, as the latest anchor always wins."""
    spans = {}

    if correction.base_anchor != capture_time:
        spans[correction.base_anchor] = list(correction.geometry)

    spans.update(_copied(correction.overrides))
    overrides = _copied(history.overrides)

    if spans:
        first, last = min(spans), max(spans)
        overrides = {
            anchor: geometry
            for anchor, geometry in overrides.items()
            if not first < anchor < last
        }
        overrides.update(spans)

    return overrides


def merged_absences(history, correction, capture_time):
    """(absent_at, absent_from, absent_until) of two merged ROIs: absent
    only where both were, and present on the shown image (captured at
    ``capture_time``). None when that needs a hole in a range covering
    the image from both sides.

    Exact where it can be with one point list and two half-open ranges:
    a point either ROI was deleted at stays when the other was deleted
    there too (by a point or a range); a "later" range stays only if both
    had one (the later start), an "earlier" one likewise (the earlier
    end). One ROI's "later" crossed with the other's "earlier" is a
    bounded stretch the two ranges cannot express: it is left out, the
    ROI shown there rather than lost. A range starting or ending exactly
    on the shown image is moved just past it, keeping every other image
    it covered — captures still to come included."""
    points = {*history.absent_at, *correction.absent_at}
    absent_at = sorted(
        time
        for time in points
        if time != capture_time
        and history.absent_by(time)
        and correction.absent_by(time)
    )
    absent_from = (
        max(history.absent_from, correction.absent_from)
        if not math.isnan(history.absent_from + correction.absent_from)
        else math.nan
    )
    absent_until = (
        min(history.absent_until, correction.absent_until)
        if not math.isnan(history.absent_until + correction.absent_until)
        else math.nan
    )

    if capture_time >= absent_from:
        if capture_time > absent_from:
            return None

        absent_from = math.nextafter(capture_time, math.inf)

    if capture_time <= absent_until:
        if capture_time < absent_until:
            return None

        absent_until = math.nextafter(capture_time, -math.inf)

    return absent_at, absent_from, absent_until


class MergeRoiOnImageCommand(_SessionCommand):
    """Merge two ROIs' definitions into one, per image: ``roi`` (the
    history) survives with its identity — id, plot line, CSV column,
    style, expected values — takes ``merged_name``, and on every image has
    ``replacement``'s shape (the correction drawn on the shown image)
    where that defined one and its own elsewhere (merged_overrides);
    on the shown image it has the correction's shape. It is absent only
    where both were (merged_absences). The correction goes, untouched,
    so an undo puts it back exactly."""

    #: The surviving ROI, with the history.
    roi = Instance(Roi)

    #: The correction merged into it and removed from the session.
    replacement = Instance(Roi)

    #: Capture time of the shown image.
    capture_time = Float()

    #: The surviving ROI's name after the merge — the name the user
    #: typed ('' keeps its own). Not ``name``: that is the command's own
    #: undo-stack label.
    merged_name = Str()

    #: ``roi``'s name, overrides, single-image shapes and absences before
    #: the merge: (name, overrides, local_overrides, absent_at,
    #: absent_from, absent_until).
    _before = Tuple(Str, Any, Any, List, Float, Float)

    #: Where the replacement stood in the ROI list, for the undo.
    _pairs = List(Tuple(Int, Instance(Roi)))

    def _name_default(self):
        return f"Merge {self.replacement.name} into {self.merged_name or self.roi.name}"

    def do(self):
        roi = self.roi
        self._before = (
            roi.name,
            _copied(roi.overrides),
            _copied(roi.local_overrides),
            list(roi.absent_at),
            roi.absent_from,
            roi.absent_until,
        )
        self.redo()

    def undo(self):
        name, overrides, local_overrides, absent_at, absent_from, absent_until = (
            self._before
        )
        self.roi.trait_set(
            name=name,
            overrides=_copied(overrides),
            local_overrides=_copied(local_overrides),
            absent_at=list(absent_at),
            absent_from=absent_from,
            absent_until=absent_until,
        )
        _insert_into_session(self.session, self._pairs)

    def redo(self):
        roi, replacement, capture_time = self.roi, self.replacement, self.capture_time
        absences = merged_absences(roi, replacement, capture_time)
        # The controller checks first; a stale redo keeps the history's.
        absent_at, absent_from, absent_until = absences or (
            list(roi.absent_at),
            roi.absent_from,
            roi.absent_until,
        )
        # Fresh dicts and lists: the canvas and the table follow them by
        # assignment.
        roi.trait_set(
            name=self.merged_name or roi.name,
            overrides=merged_overrides(roi, replacement, capture_time),
            local_overrides={
                **_copied(roi.local_overrides),
                **_copied(replacement.local_overrides),
                capture_time: replacement.effective_geometry(capture_time),
            },
            absent_at=absent_at,
            absent_from=absent_from,
            absent_until=absent_until,
        )
        self._pairs = _remove_from_session(self.session, [replacement])
