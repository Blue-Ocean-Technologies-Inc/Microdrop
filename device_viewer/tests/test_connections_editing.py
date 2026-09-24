# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Unit tests for hand editing the device connections (Qt-free)."""

# Standard library imports.
from pathlib import Path

# Third-party imports.
import numpy as np
import pytest

# Microdrop package imports.
from device_viewer.models.connections_editor import ConnectionsEditorModel
from device_viewer.utils.dmf_utils import SvgUtil
from device_viewer.utils.snapping import nearest_point_index_within

BUNDLED_2X3 = (
    Path(__file__).resolve().parents[1] / "resources" / "devices" / "2x3device.svg"
)


@pytest.fixture
def svg_model():
    svg_model = SvgUtil(filename=str(BUNDLED_2X3))
    svg_model.connections_modified = False

    return svg_model


def unconnected_pair(svg_model):
    """Two electrodes of the device that are not neighbours."""
    return next(
        (from_id, to_id)
        for from_id in svg_model.electrode_centers
        for to_id in svg_model.electrode_centers
        if from_id != to_id and to_id not in svg_model.neighbours.get(from_id, [])
    )


def test_add_connection_links_both_directions(svg_model):
    from_id, to_id = unconnected_pair(svg_model)

    svg_model.add_connection(from_id, to_id)

    assert to_id in svg_model.neighbours[from_id]
    assert from_id in svg_model.neighbours[to_id]
    assert (from_id, to_id) in svg_model.connections
    assert (to_id, from_id) in svg_model.connections
    assert svg_model.connections_modified


def test_add_connection_ignores_self_and_existing(svg_model):
    from_id, neighbour_ids = next(iter(svg_model.neighbours.items()))
    before = {key: list(ids) for key, ids in svg_model.neighbours.items()}

    svg_model.add_connection(from_id, from_id)
    svg_model.add_connection(from_id, neighbour_ids[0])

    assert svg_model.neighbours == before
    assert not svg_model.connections_modified


def test_remove_selected_disconnects_either_direction(svg_model):
    from_id, neighbour_ids = next(iter(svg_model.neighbours.items()))
    to_id = neighbour_ids[0]
    model = ConnectionsEditorModel(
        svg_model=svg_model, selected_connections=[(to_id, from_id)]
    )

    model.remove_selected()

    assert to_id not in svg_model.neighbours[from_id]
    assert from_id not in svg_model.neighbours[to_id]
    assert (from_id, to_id) not in svg_model.connections
    assert (to_id, from_id) not in svg_model.connections
    assert model.selected_connections == []
    assert svg_model.connections_modified


def test_model_add_connection_can_be_undone_and_redone(svg_model):
    from_id, to_id = unconnected_pair(svg_model)
    model = ConnectionsEditorModel(svg_model=svg_model)
    before = {key: list(ids) for key, ids in svg_model.neighbours.items()}

    model.add_connection(from_id, to_id)

    assert to_id in svg_model.neighbours[from_id]
    assert model.can_undo
    assert not model.can_redo

    assert model.undo() is True

    assert svg_model.neighbours == before
    assert not model.can_undo
    assert model.can_redo

    assert model.redo() is True

    assert to_id in svg_model.neighbours[from_id]
    assert not model.can_redo


def test_model_remove_selected_can_be_undone(svg_model):
    from_id, neighbour_ids = next(iter(svg_model.neighbours.items()))
    to_id = neighbour_ids[0]
    before = {key: list(ids) for key, ids in svg_model.neighbours.items()}
    model = ConnectionsEditorModel(
        svg_model=svg_model, selected_connections=[(to_id, from_id)]
    )

    model.remove_selected()

    assert to_id not in svg_model.neighbours[from_id]
    assert model.can_undo

    assert model.undo() is True

    assert svg_model.neighbours == before


def test_model_undo_redo_are_no_ops_with_empty_stacks(svg_model):
    model = ConnectionsEditorModel(svg_model=svg_model)

    assert model.undo() is False
    assert model.redo() is False
    assert not model.can_undo
    assert not model.can_revert


def test_model_add_connection_ignored_edit_takes_no_snapshot(svg_model):
    from_id, neighbour_ids = next(iter(svg_model.neighbours.items()))
    model = ConnectionsEditorModel(svg_model=svg_model)

    model.add_connection(from_id, neighbour_ids[0])

    assert not model.can_undo
    assert not model.can_revert


def test_model_revert_all_restores_baseline_and_is_undoable(svg_model):
    from_id, to_id = unconnected_pair(svg_model)
    baseline = {key: list(ids) for key, ids in svg_model.neighbours.items()}
    model = ConnectionsEditorModel(svg_model=svg_model)

    assert not model.can_revert

    model.add_connection(from_id, to_id)

    assert model.can_revert

    model.revert_all()

    assert svg_model.neighbours == baseline
    assert not model.can_revert
    assert model.can_undo

    assert model.undo() is True

    assert to_id in svg_model.neighbours[from_id]


def test_model_revert_all_is_a_no_op_when_nothing_changed(svg_model):
    baseline = {key: list(ids) for key, ids in svg_model.neighbours.items()}
    model = ConnectionsEditorModel(svg_model=svg_model)

    model.revert_all()

    assert svg_model.neighbours == baseline
    assert not model.can_undo


def test_model_new_edit_after_undo_clears_redo_stack(svg_model):
    from_id, to_id = unconnected_pair(svg_model)
    model = ConnectionsEditorModel(svg_model=svg_model)

    model.add_connection(from_id, to_id)
    model.undo()

    assert model.can_redo

    # Undo restored the pair to unconnected; reconnecting is a fresh edit
    # that should fork history and drop the redo entry.
    model.add_connection(from_id, to_id)

    assert not model.can_redo


def test_nearest_point_index_within():
    points = np.array([[0.0, 0.0], [10.0, 0.0]])

    assert nearest_point_index_within(points, 9.0, 1.0, max_distance=2.0) == 1
    assert nearest_point_index_within(points, 5.0, 5.0, max_distance=2.0) is None
