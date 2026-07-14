"""Keyboard shortcuts for the navigation-bar buttons (#517).

Each shortcut is scoped to the protocol pane (WidgetWithChildrenShortcut),
so it fires when the tree — a child of the pane — has focus, and clicks its
button only when that button is visible and enabled.
"""
from pyface.qt.QtCore import Qt
from pyface.qt.QtTest import QTest

from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane


def _shown_pane(qapp):
    pane = ProtocolTreePane([make_name_column()])
    pane.manager.add_step(values={"name": "A"})
    pane.show()
    qapp.processEvents()
    return pane


def test_nav_shortcut_fires_on_focused_tree(qapp):
    """A nav shortcut fires while the tree (child of the pane) has focus —
    the whole point of the WidgetWithChildrenShortcut scope. 'S' is Next
    Step in the current scheme."""
    pane = _shown_pane(qapp)
    fired = []
    pane.navigation_bar.btn_next.clicked.connect(lambda: fired.append(1))
    pane.widget.tree.setFocus()
    qapp.processEvents()
    QTest.keyClick(pane.widget.tree, Qt.Key_S)
    qapp.processEvents()
    assert fired == [1]


def test_all_nav_shortcuts_installed_with_tooltips(qapp):
    pane = _shown_pane(qapp)
    keys = {s.key().toString() for s in pane._nav_shortcuts}
    assert keys == {
        "W", "S", "A", "D", "Ctrl+Left", "Ctrl+Right", "Ctrl+.", "Ctrl+R",
    }
    # Discoverability: the shortcut is surfaced in the tooltip.
    assert "(" in pane.navigation_bar.btn_next.toolTip()
    assert "Ctrl" in pane.navigation_bar.btn_play.toolTip()
    assert "Ctrl" in pane.navigation_bar.btn_resume.toolTip()


def test_shortcut_skips_disabled_and_hidden_buttons(qapp):
    pane = _shown_pane(qapp)
    nb = pane.navigation_bar
    # Stop starts disabled; the phase buttons start hidden (not phase mode).
    stop_fired, phase_fired = [], []
    nb.btn_stop.clicked.connect(lambda: stop_fired.append(1))
    nb.btn_prev_phase.clicked.connect(lambda: phase_fired.append(1))
    assert pane._click_if_active(nb.btn_stop) is False
    assert pane._click_if_active(nb.btn_prev_phase) is False
    assert stop_fired == [] and phase_fired == []


def test_play_shortcut_targets_visible_control_in_each_mode(qapp):
    pane = _shown_pane(qapp)
    nb = pane.navigation_bar
    play_fired, resume_fired = [], []
    nb.btn_play.clicked.connect(lambda: play_fired.append(1))
    nb.btn_resume.clicked.connect(lambda: resume_fired.append(1))

    # Normal mode: play is visible, resume hidden.
    pane._activate_play()
    assert play_fired == [1] and resume_fired == []

    # Phase-by-phase mode: play hidden, resume visible.
    nb.split_play_button_to_phase_controls()
    qapp.processEvents()
    play_fired.clear()
    resume_fired.clear()
    pane._activate_play()
    assert resume_fired == [1] and play_fired == []
