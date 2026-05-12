"""Integration tests for the PPT-10.3 file-menu plumbing on
``ProtocolTreePane`` — dirty bookkeeping, save/load wrappers, guard
prompts, and the application_exiting veto.

These use the ``qapp`` fixture so the pane can construct its real Qt
widgets. File IO and confirm dialogs are patched.
"""

import json
from unittest.mock import patch

import pytest

from microdrop_application.dialogs.pyface_wrapper import NO, YES


def _build_pane(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    return ProtocolTreePane([make_type_column(), make_name_column()])


# --- dirty bookkeeping ---------------------------------------------------

def test_starts_clean_with_untitled_name(qapp):
    pane = _build_pane(qapp)
    t = pane.protocol_state_tracker
    assert t.is_modified is False
    assert t.protocol_name == "untitled"
    assert t.loaded_protocol_path == ""


def test_mutation_marks_dirty(qapp):
    pane = _build_pane(qapp)
    pane.manager.add_step()
    assert pane.protocol_state_tracker.is_modified is True


def test_save_as_clears_dirty_and_sets_path(qapp, tmp_path):
    pane = _build_pane(qapp)
    pane.manager.add_step()
    assert pane.protocol_state_tracker.is_modified is True

    target = tmp_path / "out.json"
    with patch(
        "pluggable_protocol_tree.views.protocol_tree_pane.QFileDialog"
    ) as QFD:
        QFD.getSaveFileName.return_value = (str(target), "Protocol JSON (*.json)")
        pane.save_as_protocol_dialog()

    assert target.exists()
    assert pane.protocol_state_tracker.is_modified is False
    assert pane.protocol_state_tracker.protocol_name == "out"
    assert pane.protocol_state_tracker.loaded_protocol_path == str(target)


def test_save_uses_known_path_without_dialog(qapp, tmp_path):
    pane = _build_pane(qapp)
    target = tmp_path / "first.json"
    pane.protocol_state_tracker.set_saved(str(target))
    pane.manager.add_step()                    # dirty again

    with patch(
        "pluggable_protocol_tree.views.protocol_tree_pane.QFileDialog"
    ) as QFD:
        pane.save_protocol_dialog()
        QFD.getSaveFileName.assert_not_called()

    assert target.exists()
    assert pane.protocol_state_tracker.is_modified is False


def test_save_without_known_path_falls_back_to_dialog(qapp, tmp_path):
    pane = _build_pane(qapp)
    pane.manager.add_step()
    target = tmp_path / "fallback.json"

    with patch(
        "pluggable_protocol_tree.views.protocol_tree_pane.QFileDialog"
    ) as QFD:
        QFD.getSaveFileName.return_value = (str(target), "Protocol JSON (*.json)")
        pane.save_protocol_dialog()
        QFD.getSaveFileName.assert_called_once()

    assert target.exists()
    assert pane.protocol_state_tracker.loaded_protocol_path == str(target)


# --- load + guards -------------------------------------------------------

def _write_minimal_protocol(path):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.models.row_manager import RowManager

    rm = RowManager(columns=[make_type_column(), make_name_column()])
    rm.add_step(values={"name": "from-disk"})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rm.to_json(), f)


def test_load_clears_dirty_and_sets_path(qapp, tmp_path):
    pane = _build_pane(qapp)
    fixture = tmp_path / "in.json"
    _write_minimal_protocol(fixture)

    with patch(
        "pluggable_protocol_tree.views.protocol_tree_pane.QFileDialog"
    ) as QFD:
        QFD.getOpenFileName.return_value = (str(fixture), "Protocol JSON (*.json)")
        pane.load_protocol_dialog()

    assert pane.protocol_state_tracker.is_modified is False
    assert pane.protocol_state_tracker.protocol_name == "in"
    assert pane.protocol_state_tracker.loaded_protocol_path == str(fixture)
    assert len(pane.manager.root.children) == 1


def test_load_aborts_on_user_no_when_dirty(qapp, tmp_path):
    pane = _build_pane(qapp)
    pane.manager.add_step()                    # mark dirty

    fixture = tmp_path / "in.json"
    _write_minimal_protocol(fixture)

    with patch(
        "pluggable_protocol_tree.views.protocol_tree_pane.QFileDialog"
    ) as QFD, patch(
        "pluggable_protocol_tree.views.protocol_tree_pane.confirm",
        return_value=NO,
    ):
        pane.load_protocol_dialog()
        QFD.getOpenFileName.assert_not_called()

    assert pane.protocol_state_tracker.is_modified is True
    # Manager untouched — still has the single step we added.
    assert len(pane.manager.root.children) == 1
    assert pane.manager.root.children[0].name != "from-disk"


def test_load_proceeds_on_user_yes_when_dirty(qapp, tmp_path):
    pane = _build_pane(qapp)
    pane.manager.add_step(values={"name": "before-load"})
    assert pane.protocol_state_tracker.is_modified is True

    fixture = tmp_path / "in.json"
    _write_minimal_protocol(fixture)

    with patch(
        "pluggable_protocol_tree.views.protocol_tree_pane.QFileDialog"
    ) as QFD, patch(
        "pluggable_protocol_tree.views.protocol_tree_pane.confirm",
        return_value=YES,
    ):
        QFD.getOpenFileName.return_value = (str(fixture), "Protocol JSON (*.json)")
        pane.load_protocol_dialog()

    assert pane.protocol_state_tracker.protocol_name == "in"
    assert pane.protocol_state_tracker.is_modified is False
    assert pane.manager.root.children[0].name == "from-disk"


# --- new protocol --------------------------------------------------------

def test_new_protocol_resets_manager_and_tracker(qapp, tmp_path):
    pane = _build_pane(qapp)
    pane.manager.add_step(values={"name": "before-new"})
    pane.protocol_state_tracker.set_saved(str(tmp_path / "x.json"))
    pane.manager.add_step()                   # dirty again

    pane.new_protocol()                       # clean path — no confirm needed

    assert len(pane.manager.root.children) == 0
    t = pane.protocol_state_tracker
    assert t.protocol_name == "untitled"
    assert t.loaded_protocol_path == ""
    assert t.is_modified is False


def test_new_protocol_aborts_on_user_no_when_dirty(qapp):
    pane = _build_pane(qapp)
    pane.manager.add_step(values={"name": "keepme"})    # dirty

    with patch(
        "pluggable_protocol_tree.views.protocol_tree_pane.confirm",
        return_value=NO,
    ):
        pane.new_protocol()

    assert len(pane.manager.root.children) == 1
    assert pane.manager.root.children[0].name == "keepme"
    assert pane.protocol_state_tracker.is_modified is True


# --- application_exiting veto -------------------------------------------

class _VetoableEvent:
    def __init__(self):
        self.veto = False


def test_application_exiting_does_nothing_when_clean(qapp):
    pane = _build_pane(qapp)
    ev = _VetoableEvent()
    pane._on_application_exiting(ev)
    assert ev.veto is False


def test_application_exiting_vetoes_on_dirty_no(qapp):
    pane = _build_pane(qapp)
    pane.manager.add_step()                  # dirty
    ev = _VetoableEvent()
    with patch(
        "pluggable_protocol_tree.views.protocol_tree_pane.confirm",
        return_value=NO,
    ):
        pane._on_application_exiting(ev)
    assert ev.veto is True


def test_application_exiting_proceeds_on_dirty_yes(qapp):
    pane = _build_pane(qapp)
    pane.manager.add_step()                  # dirty
    ev = _VetoableEvent()
    with patch(
        "pluggable_protocol_tree.views.protocol_tree_pane.confirm",
        return_value=YES,
    ):
        pane._on_application_exiting(ev)
    assert ev.veto is False
