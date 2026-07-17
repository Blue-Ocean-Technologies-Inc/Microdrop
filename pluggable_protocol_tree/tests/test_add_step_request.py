"""PROTOCOL_TREE_ADD_STEP insertion logic (module-level helper — the
dramatiq/Qt plumbing around it is the same Event->observe pattern as
set_cell and is not re-tested here)."""

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.models.cell_sync import ProtocolTreeAddStepMessage
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.device_viewer_sync import (
    _insert_step_from_message,
)


def _manager():
    m = RowManager(columns=[make_type_column(), make_name_column(),
                            make_duration_column()])
    m.add_step(values={"name": "A"})
    m.add_step(values={"name": "B"})
    return m


def test_insert_after_step_lands_between():
    m = _manager()
    a_uuid = m.root.children[0].uuid
    _insert_step_from_message(m, ProtocolTreeAddStepMessage(
        after_step_id=a_uuid, cells={"duration_s": 7.5}, name="Chain step"))
    names = [r.name for r in m.root.children]
    assert names == ["A", "Chain step", "B"]
    assert m.root.children[1].duration_s == 7.5


def test_insert_into_group_appends_as_last_child():
    m = _manager()
    m.add_group()
    grp = m.root.children[2]
    _insert_step_from_message(m, ProtocolTreeAddStepMessage(
        group_id=grp.uuid, cells={}, name="In group"))
    assert [r.name for r in grp.children] == ["In group"]


def test_unknown_ids_append_at_root_end():
    m = _manager()
    _insert_step_from_message(m, ProtocolTreeAddStepMessage(
        after_step_id="nope", cells={}, name="Tail"))
    assert [r.name for r in m.root.children][-1] == "Tail"


def test_unknown_columns_in_cells_are_skipped():
    m = _manager()
    _insert_step_from_message(m, ProtocolTreeAddStepMessage(
        cells={"duration_s": 2.0, "not_a_column": 1}, name="Partial"))
    assert m.root.children[-1].duration_s == 2.0
