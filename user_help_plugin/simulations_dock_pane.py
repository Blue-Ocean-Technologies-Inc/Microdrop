# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tutorial Simulations dock pane: every tutorial simulation, one at a time.

A contents tree on the left lists each tutorial with its simulations under
it; the selected simulation shows on the right. Each tutorial page loads
once, into one web view, when it is first selected while the pane is
visible; switching simulations only changes which figure the page shows, so
every simulation keeps its state.

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

#: Starting widths of the contents tree and the simulation view.
SPLITTER_SIZES = [200, 600]


def _escape_mnemonic(text):
    """Return ``text`` for a Qt button label, where a single & is a mnemonic."""
    return text.replace("&", "&&")


class TutorialSimulationsPage(QtWidgets.QWidget):
    """One tutorial page in a single web view, showing one simulation."""

    def __init__(self, record, parent=None):
        super().__init__(parent)

        self.record = record
        self._web_view = None
        self._page_ready = False
        self._simulation_index = 0

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

    def select_simulation(self, index):
        """Show the ``index``-th simulation, now or once the page is ready."""
        self._simulation_index = index
        self._show_current_simulation()

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
            f"Open {_escape_mnemonic(self.record.tutorial.title)} in the browser",
            fallback,
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

    def _show_current_simulation(self):
        if not self._page_ready:
            return

        demo = self.record.simulations[self._simulation_index].demo

        self._web_view.page().runJavaScript(f"microdropShowSim({json.dumps(demo)});")


class TutorialSimulationsDockPane(DockPane):
    """Every tutorial simulation, picked from a tutorial/simulation tree."""

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

    #: The contents: a top-level item per tutorial, a child per simulation.
    _contents_tree = Instance(QtWidgets.QTreeWidget)

    #: One page per tutorial, in the same order as the tree's tutorials.
    _pages = Instance(QtWidgets.QStackedWidget)

    def create_contents(self, parent):
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, parent)

        self._contents_tree = QtWidgets.QTreeWidget(splitter)
        self._contents_tree.setHeaderHidden(True)
        self._contents_tree.currentItemChanged.connect(self._show_current)

        self._pages = QtWidgets.QStackedWidget(splitter)

        splitter.addWidget(self._contents_tree)
        splitter.addWidget(self._pages)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes(SPLITTER_SIZES)

        self._fill_contents()

        return splitter

    @observe("model.tutorials")
    def _tutorials_changed(self, event):
        if self._contents_tree is not None:
            self._fill_contents()

    @observe("visible")
    def _visibility_changed(self, event):
        self._show_current()

    def _fill_contents(self):
        """Rebuild tree and pages, keeping the shown simulation if it stays."""
        tree = self._contents_tree
        pages = self._pages

        shown_page = pages.currentWidget()
        shown_item = tree.currentItem()
        shown_tutorial = shown_page.record.tutorial.title if shown_page else None
        shown_simulation = shown_item.text(0) if shown_item else None

        tree.blockSignals(True)
        tree.clear()

        while pages.count():
            page = pages.widget(0)
            pages.removeWidget(page)
            page.deleteLater()

        selected = None

        for record in self.model.tutorials:
            pages.addWidget(TutorialSimulationsPage(record, pages))

            tutorial_item = QtWidgets.QTreeWidgetItem(tree, [record.label])
            tutorial_item.setToolTip(0, record.tutorial.title)

            for simulation in record.simulations:
                item = QtWidgets.QTreeWidgetItem(tutorial_item, [simulation.title])
                item.setToolTip(0, f"{simulation.title} ({record.tutorial.title})")

                if (
                    record.tutorial.title == shown_tutorial
                    and simulation.title == shown_simulation
                ):
                    selected = item

        if selected is None and tree.topLevelItemCount():
            selected = tree.topLevelItem(0).child(0)

        tree.expandAll()
        tree.blockSignals(False)

        if selected is not None:
            tree.setCurrentItem(selected)

    def _show_current(self, *args):
        """Show the selected simulation; a tutorial keeps its last one shown."""
        if self._contents_tree is None:
            return

        item = self._contents_tree.currentItem()

        if item is None:
            return

        tutorial_item = item.parent() if item.parent() is not None else item
        page = self._pages.widget(
            self._contents_tree.indexOfTopLevelItem(tutorial_item)
        )

        self._pages.setCurrentWidget(page)

        if item is not tutorial_item:
            page.select_simulation(tutorial_item.indexOfChild(item))

        if self.visible:
            page.load()
