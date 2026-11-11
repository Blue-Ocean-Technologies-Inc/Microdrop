# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Which steps a device-viewer edit of the primary step is written to
(``write_back_targets``) — the Qt-free decision behind the sync service's
multi-selection write-back."""

# Third-party imports.
import pytest

# Microdrop package imports.
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.device_viewer_sync import write_back_targets


@pytest.fixture
def manager():
    """Steps A, B at the root, then group G holding steps G1, G2 and a
    nested group, then step C."""
    manager = RowManager(columns=[make_type_column(), make_name_column()])
    manager.add_step(values={"name": "A"})
    manager.add_step(values={"name": "B"})
    group = manager.add_group(name="G")
    manager.add_step(parent_path=group, values={"name": "G1"})
    manager.add_step(parent_path=group, values={"name": "G2"})
    manager.add_group(parent_path=group, name="Nested")
    manager.add_step(values={"name": "C"})

    return manager


def _uuid(manager, path):
    return manager.get_row(path).uuid


def test_single_selection_is_just_the_primary(manager):
    manager.select([(1,)])

    assert write_back_targets(manager, _uuid(manager, (1,))) == [(1,)]


def test_multi_selection_targets_every_selected_step_in_tree_order(manager):
    manager.select([(3,), (0,), (1,)])

    assert write_back_targets(manager, _uuid(manager, (1,))) == [(0,), (1,), (3,)]


def test_primary_outside_the_selection_is_written_alone(manager):
    manager.select([(0,), (1,)])

    assert write_back_targets(manager, _uuid(manager, (3,))) == [(3,)]


def test_selected_group_contributes_its_direct_child_steps(manager):
    manager.select([(0,), (2,)])

    assert write_back_targets(manager, _uuid(manager, (2, 0))) == [
        (0,),
        (2, 0),
        (2, 1),
    ]


def test_group_or_unknown_primary_has_no_targets(manager):
    manager.select([(0,), (2,)])

    assert write_back_targets(manager, _uuid(manager, (2,))) == []
    assert write_back_targets(manager, "no-such-step") == []
