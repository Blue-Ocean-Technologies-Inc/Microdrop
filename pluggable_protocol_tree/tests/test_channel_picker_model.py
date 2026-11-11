# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The channel picker model's entry bookkeeping and view requests."""

# Enthought library imports.
from traits.api import Float, HasTraits, Instance, List, observe

# Microdrop package imports.
from pluggable_protocol_tree.models.channel_picker_model import (
    ROTATE_STEP_DEG,
    ZOOM_STEP_FACTOR,
    ChannelPickerModel,
)


class _ZoomRecorder(HasTraits):
    """Collects the zoom factors a model requests."""

    model = Instance(ChannelPickerModel, ())
    zooms = List(Float)

    @observe("model:zoom_requested")
    def _record(self, event):
        self.zooms.append(event.new)


def test_opens_with_one_empty_entry_selected():
    model = ChannelPickerModel()

    assert model.entries == [[]]
    assert model.current_index == 0
    assert model.entry_labels == ["Entry 1: none"]
    assert model.current_label == "Entry 1: none"


def test_opens_on_the_first_given_entry():
    model = ChannelPickerModel(entries=[[1, 2], [3]])

    assert model.current_index == 0
    assert model.current_channels == [1, 2]
    assert model.entry_labels == ["Entry 1: 1, 2", "Entry 2: 3"]


def test_toggle_adds_and_removes_a_channel_in_the_current_entry():
    model = ChannelPickerModel(entries=[[1], [3]], current_index=1)

    model.toggle_channel(2)

    assert model.entries == [[1], [2, 3]]
    assert model.current_label == "Entry 2: 2, 3"

    model.toggle_channel(3)

    assert model.entries == [[1], [2]]
    assert model.current_channels == [2]


def test_toggle_without_a_current_entry_starts_one():
    model = ChannelPickerModel(entries=[[1]])
    model.current_index = -1

    model.toggle_channel(4)

    assert model.entries == [[1], [4]]
    assert model.current_index == 1


def test_add_entry_appends_and_selects_it():
    model = ChannelPickerModel(entries=[[1]])

    model.add_entry = True

    assert model.entries == [[1], []]
    assert model.current_index == 1


def test_remove_entry_keeps_the_index_in_range():
    model = ChannelPickerModel(entries=[[1], [2], [3]], current_index=2)

    model.remove_entry = True

    assert model.entries == [[1], [2]]
    assert model.current_index == 1

    model.current_index = 0
    model.remove_entry = True

    assert model.entries == [[2]]
    assert model.current_index == 0

    model.remove_entry = True

    assert model.entries == []
    assert model.current_index == -1
    assert model.current_label == ""

    model.remove_entry = True

    assert model.entries == []


def test_clear_entry_empties_only_the_current_entry():
    model = ChannelPickerModel(entries=[[1, 2], [3]])

    model.clear_entry = True

    assert model.entries == [[], [3]]
    assert model.entry_labels == ["Entry 1: none", "Entry 2: 3"]


def test_view_requests():
    recorder = _ZoomRecorder()
    model = recorder.model

    model.zoom_in = True
    model.zoom_out = True

    for _ in range(5):
        model.rotate = True

    assert recorder.zooms == [ZOOM_STEP_FACTOR, 1 / ZOOM_STEP_FACTOR]
    assert model.rotation == (5 * ROTATE_STEP_DEG) % 360
