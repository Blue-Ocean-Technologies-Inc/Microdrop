"""Clickable, theme-aware experiment label.

Ported from ``protocol_grid/extra_ui_elements.py`` ``ExperimentLabel``
(legacy). Stays in pluggable_protocol_tree so PPT-9 can delete
protocol_grid without breaking the new dock pane.
"""

from pyface.qt.QtCore import Qt, Signal
from pyface.qt.QtGui import QAction, QContextMenuEvent
from pyface.qt.QtWidgets import QApplication, QLabel, QMenu

from microdrop_style.helpers import is_dark_mode


class ExperimentLabel(QLabel):
    """QLabel that emits ``clicked`` on left-click and renders the
    active experiment id with a theme-aware link colour. Right-click
    opens a context menu with an Enable Tooltip toggle."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText("<b>Experiment: </b>")
        self.setToolTip("Active Experiment (Click to open folder)")
        self.setCursor(Qt.PointingHandCursor)

        self._experiment_id = None
        self._tooltip_visible = True

        self.apply_styling()
        QApplication.styleHints().colorSchemeChanged.connect(self.apply_styling)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)

    def handle_tooltip_toggle(self, checked):
        self._tooltip_visible = checked
        if checked:
            self.setToolTip("Active Experiment (Click to open folder)")
        else:
            self.setToolTip("")

    def contextMenuEvent(self, event: QContextMenuEvent):
        menu = QMenu(self)
        action = QAction("Enable Tooltip", checkable=True,
                         checked=self._tooltip_visible)
        action.triggered.connect(self.handle_tooltip_toggle)
        menu.addAction(action)
        menu.exec(event.globalPos())

    def update_experiment_id(self, experiment_id=None):
        if experiment_id is None:
            experiment_id = self._experiment_id
        if experiment_id is None:
            self.setText("<b>Experiment: </b>")
            return
        link_color = "#82B1FF" if is_dark_mode() else "#0066CC"
        self.setText(
            f"<b>Experiment: </b> "
            f"<span style='text-decoration: underline; color: {link_color};'>"
            f"{experiment_id}</span>"
        )
        self._experiment_id = experiment_id

    def apply_styling(self):
        text_color = "#f0f0f0" if is_dark_mode() else "#333333"
        hover_bg = "#3a3a3a" if is_dark_mode() else "#e0e0e0"
        self.setStyleSheet(
            f"QLabel {{ color: {text_color}; border: none; }}"
            f"QLabel:hover {{ background-color: {hover_bg}; }}"
        )
        self.update_experiment_id()
