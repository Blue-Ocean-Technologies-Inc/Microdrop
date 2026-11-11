# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free state of the channel picker: the Fill Pattern's channel entries
(one per step of the pattern), which entry the device picture edits, the
device geometry it draws, and the view requests (zoom, fit, rotate) its
canvas follows."""

# Enthought library imports.
from traits.api import (
    Array,
    Button,
    Dict,
    Event,
    Float,
    HasTraits,
    Int,
    List,
    Property,
    Str,
    Union,
    observe,
)

#: View scale change per zoom click or wheel notch.
ZOOM_STEP_FACTOR = 1.25

#: Degrees one Rotate click turns the device picture (clockwise).
ROTATE_STEP_DEG = 90


class ChannelPickerModel(HasTraits):
    """Channel entries being picked on a picture of the device."""

    #: The pattern's channel entries, one per step, each a sorted list.
    entries = List(List(Int))

    #: Index of the entry the device picture shows and edits; -1 for none.
    current_index = Int(-1)

    #: "Entry 1: 1, 2, 3" labels of ``entries``, for the entry list.
    entry_labels = Property(List(Str), observe="entries.items")

    #: Label of the current entry. The list editor re-selects its row by
    #: this label after the labels are rebuilt, so the selection survives
    #: an edit of the current entry.
    current_label = Str()

    #: Channels of the current entry (empty when there is none).
    current_channels = Property(List(Int), observe="entries.items, current_index")

    #: Device geometry: {electrode id: (N, 2) vertex array}, y down.
    electrode_paths = Dict(Str, Array)

    #: {electrode id: channel}; None for an electrode without one.
    electrode_channels = Dict(Str, Union(None, Int))

    #: Clockwise rotation of the device picture, in degrees.
    rotation = Int(0)

    #: Scale the canvas by this factor (zoom in > 1, zoom out < 1).
    zoom_requested = Event(Float)

    #: Fit the whole device in the canvas at the current rotation.
    fit_requested = Event()

    add_entry = Button()
    remove_entry = Button()
    clear_entry = Button()
    zoom_in = Button()
    zoom_out = Button()
    fit_view = Button()
    rotate = Button()

    def traits_init(self):
        if not self.entries:
            self.entries = [[]]

        if not 0 <= self.current_index < len(self.entries):
            self.current_index = 0

        self._update_current_label()

    # --- property getters ---

    def _get_entry_labels(self):
        return [
            f"Entry {index + 1}: {', '.join(map(str, entry)) or 'none'}"
            for index, entry in enumerate(self.entries)
        ]

    def _get_current_channels(self):
        if 0 <= self.current_index < len(self.entries):
            return list(self.entries[self.current_index])

        return []

    # --- entry editing ---

    def toggle_channel(self, channel):
        """Add ``channel`` to the current entry, or take it out; with no
        current entry, start a new one."""
        if not 0 <= self.current_index < len(self.entries):
            self._append_entry()

        channels = set(self.entries[self.current_index]) ^ {channel}
        self.entries[self.current_index] = sorted(channels)

    def _append_entry(self):
        self.entries.append([])
        self.current_index = len(self.entries) - 1

    @observe("add_entry")
    def _add_entry_fired(self, event):
        self._append_entry()

    @observe("remove_entry")
    def _remove_entry_fired(self, event):
        if not 0 <= self.current_index < len(self.entries):
            return

        index = self.current_index
        del self.entries[index]
        self.current_index = min(index, len(self.entries) - 1)

    @observe("clear_entry")
    def _clear_entry_fired(self, event):
        if 0 <= self.current_index < len(self.entries):
            self.entries[self.current_index] = []

    @observe("entries.items, current_index", post_init=True)
    def _update_current_label(self, event=None):
        labels = self.entry_labels
        index = self.current_index
        self.current_label = labels[index] if 0 <= index < len(labels) else ""

    # --- view requests ---

    @observe("zoom_in")
    def _zoom_in_fired(self, event):
        self.zoom_requested = ZOOM_STEP_FACTOR

    @observe("zoom_out")
    def _zoom_out_fired(self, event):
        self.zoom_requested = 1 / ZOOM_STEP_FACTOR

    @observe("fit_view")
    def _fit_view_fired(self, event):
        self.fit_requested = True

    @observe("rotate")
    def _rotate_fired(self, event):
        self.rotation = (self.rotation + ROTATE_STEP_DEG) % 360
