"""Tests for the ported ExperimentLabel widget."""

from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QMouseEvent
from pyface.qt.QtCore import QPointF


def test_label_default_text_when_no_experiment(qapp):
    from pluggable_protocol_tree.views.experiment_label import ExperimentLabel
    lbl = ExperimentLabel()
    assert "Experiment" in lbl.text()


def test_update_experiment_id_renders_id(qapp):
    from pluggable_protocol_tree.views.experiment_label import ExperimentLabel
    lbl = ExperimentLabel()
    lbl.update_experiment_id("2026-05-08T12-00-00Z")
    assert "2026-05-08T12-00-00Z" in lbl.text()


def test_update_experiment_id_remembers_last_value(qapp):
    from pluggable_protocol_tree.views.experiment_label import ExperimentLabel
    lbl = ExperimentLabel()
    lbl.update_experiment_id("exp-1")
    # Calling with None re-renders the last set id (used by theme-change re-style).
    lbl.update_experiment_id(None)
    assert "exp-1" in lbl.text()


def test_left_click_emits_clicked(qapp):
    from pluggable_protocol_tree.views.experiment_label import ExperimentLabel
    lbl = ExperimentLabel()
    fired = []
    lbl.clicked.connect(lambda: fired.append(True))
    event = QMouseEvent(
        QMouseEvent.MouseButtonPress, QPointF(0, 0),
        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier,
    )
    lbl.mousePressEvent(event)
    assert fired == [True]


def test_right_click_does_not_emit_clicked(qapp):
    from pluggable_protocol_tree.views.experiment_label import ExperimentLabel
    lbl = ExperimentLabel()
    fired = []
    lbl.clicked.connect(lambda: fired.append(True))
    event = QMouseEvent(
        QMouseEvent.MouseButtonPress, QPointF(0, 0),
        Qt.RightButton, Qt.RightButton, Qt.NoModifier,
    )
    lbl.mousePressEvent(event)
    assert fired == []


def test_handle_tooltip_toggle_toggles_tooltip(qapp):
    from pluggable_protocol_tree.views.experiment_label import ExperimentLabel
    lbl = ExperimentLabel()
    assert lbl.toolTip() != ""
    lbl.handle_tooltip_toggle(False)
    assert lbl.toolTip() == ""
    lbl.handle_tooltip_toggle(True)
    assert lbl.toolTip() != ""
