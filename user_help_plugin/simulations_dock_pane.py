# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tutorial Simulations dock pane: every tutorial simulation, one tab each.

An outer tab per tutorial and, inside it, a tab per simulation. Each
tutorial page loads once, into one web view, when its tab is first shown
while the pane is visible; switching simulations only changes which figure
the page shows, so every simulation keeps its state.

A web view is a raw Qt widget TraitsUI has no editor for, hence the raw Qt.
"""

# Standard library imports.
import json
import webbrowser

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets
from pyface.tasks.api import DockPane
from traits.api import Instance, observe

# Local imports.
from .consts import (
    SHOW_SIMULATION_SCRIPT_PATH,
    TUTORIAL_SIMULATIONS_DOCK_PANE_ID,
    TUTORIAL_SIMULATIONS_DOCK_PANE_NAME,
)
from .simulations import TutorialSimulationCatalog

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _tab_text(text):
    """Return ``text`` for a Qt tab label, where a single & is a mnemonic."""
    return text.replace("&", "&&")


class TutorialSimulationsTab(QtWidgets.QWidget):
    """One tutorial's simulations: a tab bar over a single web view."""

    def __init__(self, record, parent=None):
        super().__init__(parent)

        self.record = record
        self._web_view = None
        self._page_ready = False

        self._simulation_tabs = QtWidgets.QTabBar(self)
        self._simulation_tabs.setDocumentMode(True)
        self._simulation_tabs.setExpanding(False)
        self._simulation_tabs.setUsesScrollButtons(True)

        for index, simulation in enumerate(record.simulations):
            self._simulation_tabs.addTab(_tab_text(simulation.title))
            self._simulation_tabs.setTabToolTip(
                index, f"{simulation.title} ({record.tutorial.title})"
            )

        self._simulation_tabs.currentChanged.connect(self._show_current_simulation)

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addWidget(self._simulation_tabs)

    def load(self):
        """Load the tutorial page on first use."""
        if self._web_view is not None:
            return

        # Imported here so QtWebEngine only starts once a simulation is shown.
        try:
            from pyface.qt.QtWebKit import QWebView
        except ImportError as error:
            # QtWebEngine cannot load on some rigs (e.g. missing system
            # libraries on the portable Pi): offer the page in a browser.
            logger.warning(f"QtWebEngine unavailable ({error}); no in-pane view.")
            self._web_view = self._browser_fallback()
            self._layout.addWidget(self._web_view, 1)

            return

        self._web_view = QWebView(self)
        self._web_view.loadFinished.connect(self._on_load_finished)
        self._web_view.load(QtCore.QUrl.fromLocalFile(str(self.record.tutorial.path)))
        self._layout.addWidget(self._web_view, 1)

    def _browser_fallback(self):
        """Return a widget opening the whole tutorial in the system browser."""
        fallback = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(fallback)

        label = QtWidgets.QLabel(
            "Simulations cannot be shown inside MicroDrop on this computer.",
            fallback,
        )
        label.setWordWrap(True)

        button = QtWidgets.QPushButton(
            f"Open {_tab_text(self.record.tutorial.title)} in the browser", fallback
        )
        button.clicked.connect(
            lambda: webbrowser.open(self.record.tutorial.path.as_uri())
        )

        layout.addWidget(label)
        layout.addWidget(button)
        layout.addStretch(1)

        return fallback

    def _on_load_finished(self, ok):
        if not ok:
            logger.error(f"Failed to load tutorial page {self.record.tutorial.path}")
            return

        try:
            script = SHOW_SIMULATION_SCRIPT_PATH.read_text(encoding="utf-8")
        except OSError as error:
            logger.error(f"Cannot read {SHOW_SIMULATION_SCRIPT_PATH}: {error}")
            return

        self._web_view.page().runJavaScript(script)
        self._page_ready = True
        self._show_current_simulation()

    def _show_current_simulation(self, *args):
        if not self._page_ready:
            return

        index = self._simulation_tabs.currentIndex()
        demo = self.record.simulations[index].demo

        self._web_view.page().runJavaScript(f"microdropShowSim({json.dumps(demo)});")


class TutorialSimulationsDockPane(DockPane):
    """Every tutorial simulation, a tab per tutorial and per simulation."""

    #### 'ITaskPane' interface ################################################

    id = TUTORIAL_SIMULATIONS_DOCK_PANE_ID
    name = TUTORIAL_SIMULATIONS_DOCK_PANE_NAME

    #### 'IDockPane' interface ################################################

    dock_area = "right"

    #: Hidden until opened from Help, so QtWebEngine never starts unasked.
    visible = False

    #### 'TutorialSimulationsDockPane' interface ##############################

    #: The simulations to show, following the Help > Tutorials catalog.
    model = Instance(TutorialSimulationCatalog, ())

    #: The outer, one-per-tutorial tab widget.
    _tutorial_tabs = Instance(QtWidgets.QTabWidget)

    def create_contents(self, parent):
        self._tutorial_tabs = QtWidgets.QTabWidget(parent)
        self._tutorial_tabs.setDocumentMode(True)
        self._tutorial_tabs.setUsesScrollButtons(True)
        self._tutorial_tabs.currentChanged.connect(self._load_current_tutorial)

        self._fill_tutorial_tabs()

        return self._tutorial_tabs

    @observe("model.tutorials")
    def _tutorials_changed(self, event):
        if self._tutorial_tabs is not None:
            self._fill_tutorial_tabs()

    @observe("visible")
    def _visibility_changed(self, event):
        self._load_current_tutorial()

    def _fill_tutorial_tabs(self):
        """Rebuild the tabs, keeping the shown tutorial selected if it stays."""
        tabs = self._tutorial_tabs
        current = tabs.currentWidget()
        current_title = current.record.tutorial.title if current else None

        tabs.blockSignals(True)

        while tabs.count():
            page = tabs.widget(0)
            tabs.removeTab(0)
            page.deleteLater()

        for record in self.model.tutorials:
            index = tabs.addTab(
                TutorialSimulationsTab(record, tabs), _tab_text(record.label)
            )
            tabs.setTabToolTip(index, record.tutorial.title)

            if record.tutorial.title == current_title:
                tabs.setCurrentIndex(index)

        tabs.blockSignals(False)

        self._load_current_tutorial()

    def _load_current_tutorial(self, *args):
        if not self.visible or self._tutorial_tabs is None:
            return

        page = self._tutorial_tabs.currentWidget()

        if page is not None:
            page.load()
