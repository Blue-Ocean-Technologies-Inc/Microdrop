"""Tests for "Run Selected Steps" (issue #558) at the widget boundary.

The tree widget deliberately knows nothing about the executor: it decides
whether the selection is runnable, normalizes it to execution roots, and
emits ``run_selected_requested``. Whoever owns run control connects to that.
The scoping semantics themselves live in test_row_manager.py, and the
executor's honouring of ``run_paths`` in test_executor.py.
"""

import pytest

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget


@pytest.fixture
def manager():
    """Root: [A, Wash(reps=3){B, C}, Empty]."""
    rm = RowManager(columns=[make_type_column(), make_id_column(),
                             make_name_column(), make_duration_column()])
    rm.add_step(values={"name": "A"})
    g = rm.add_group(name="Wash")
    setattr(rm.get_row(g), "repetitions", 3)
    rm.add_step(parent_path=g, values={"name": "B"})
    rm.add_step(parent_path=g, values={"name": "C"})
    rm.add_group(name="Empty")
    return rm


@pytest.fixture
def widget(qapp, manager):
    return ProtocolTreeWidget(manager)


def _emitted(widget):
    received = []
    widget.run_selected_requested.connect(received.append)
    return received


# --- runnability guard ---------------------------------------------------

def test_empty_selection_is_not_runnable(widget):
    assert widget._can_run_selection() is False


def test_selecting_a_step_is_runnable(widget, manager):
    manager.select([(0,)])
    assert widget._can_run_selection() is True


def test_selecting_only_an_empty_group_is_not_runnable(widget, manager):
    """It normalizes to a root but expands to no frames — the case that
    would otherwise start a run that does nothing."""
    manager.select([(2,)])
    assert widget._can_run_selection() is False


def test_empty_group_alongside_a_real_step_is_runnable(widget, manager):
    manager.select([(0,), (2,)])
    assert widget._can_run_selection() is True


# --- request emission ----------------------------------------------------

def test_run_selected_emits_normalized_roots(widget, manager):
    received = _emitted(widget)
    # Group plus one of its own children: the child is already covered.
    manager.select([(1, 0), (1,), (0,)])
    widget._run_selected()
    assert received == [[(0,), (1,)]]


def test_run_selected_stays_silent_when_nothing_would_run(widget, manager):
    received = _emitted(widget)
    manager.select([(2,)])
    widget._run_selected()
    assert received == []


# --- run lock ------------------------------------------------------------

def test_shortcut_is_inert_while_a_run_is_in_progress(widget, manager):
    """set_editable(False) is what the dock pane calls for the duration of a
    run; the context menu is suppressed wholesale in that state, so the
    keyboard path has to be gated too."""
    received = _emitted(widget)
    manager.select([(0,)])
    widget.set_editable(False)
    widget._run_selected_shortcut()
    assert received == []
    widget.set_editable(True)
    widget._run_selected_shortcut()
    assert received == [[(0,)]]


def test_shortcut_is_inert_in_advanced_mode_during_a_run(widget, manager):
    """Advanced Mode reopens cell-value editing mid-run (#434) but not
    structural actions — and not this one."""
    received = _emitted(widget)
    manager.select([(0,)])
    widget.set_editable(True, structural=False)
    widget._run_selected_shortcut()
    assert received == []
