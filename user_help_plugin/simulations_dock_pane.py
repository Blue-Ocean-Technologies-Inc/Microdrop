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
it; the selected simulation shows on the right. Nothing is selected until
the user picks a simulation, so no web view (and no QtWebEngine) starts
with the pane. Each tutorial page loads once, into one web view, when it is
first picked while the pane is visible; switching simulations only changes
which figure the page shows, so every simulation keeps its state. A change
of the tutorial catalog keeps the pages of the tutorials still listed, and
a web view is never destroyed while it is still starting.

A web view is a raw Qt widget TraitsUI has no editor for, hence the raw Qt.
"""

# Standard library imports.
import json
import webbrowser

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from pyface.tasks.api import DockPane
from traits.api import Dict, Instance, List, observe

# Local imports.
from .consts import (
    PICK_SIMULATION_HINT,
    SHOW_SIMULATION_SCRIPT_PATH,
    TUTORIAL_SIMULATIONS_DOCK_PANE_ID,
    TUTORIAL_SIMULATIONS_DOCK_PANE_NAME,
)
from .simulations import TutorialSimulationCatalog

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Starting widths of the contents tree and the simulation view.
SPLITTER_SIZES = [230, 600]

#: How much larger a tutorial heading is than its simulations' entries.
HEADING_POINT_SIZE_INCREASE = 1.5

#: Indentation of the simulations under their tutorial heading, in pixels.
SIMULATION_INDENTATION_PX = 14

#: Roomier rows. Padding only, so the touch style's min-height still applies.
CONTENTS_TREE_STYLE_SHEET = """
    QTreeWidget { border: none; }
    QTreeWidget::item { padding: 4px 6px; }
"""


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
        self._load_finished = False
        self._retired = False
        self._simulation_index = 0

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

    def select_simulation(self, index):
        """Show the ``index``-th simulation, now or once the page is ready."""
        self._simulation_index = index
        self._show_current_simulation()

    def retire(self):
        """Delete the page, once its web view has finished starting:
        destroying a QtWebEngine view mid-start can bring the app down."""
        self._retired = True

        if self._web_view is None or self._load_finished:
            self.deleteLater()

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
        self._load_finished = True

        if self._retired:
            self.deleteLater()

            return

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

    #: The hint shown until a simulation is picked, then one page per
    #: tutorial, found through ``_pages_by_record``.
    _pages = Instance(QtWidgets.QStackedWidget)

    #: Shown in place of a page while no simulation is picked.
    _pick_hint = Instance(QtWidgets.QLabel)

    #: The page of each listed tutorial's simulations record; a record still
    #: listed after a catalog change keeps its page and web view.
    _pages_by_record = Dict()

    #: The records of the tree's tutorial items, in tree order.
    _tree_records = List()

    def create_contents(self, parent):
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, parent)

        self._contents_tree = QtWidgets.QTreeWidget(splitter)
        self._contents_tree.setHeaderHidden(True)
        self._contents_tree.setAnimated(True)
        self._contents_tree.setIndentation(SIMULATION_INDENTATION_PX)
        self._contents_tree.setStyleSheet(CONTENTS_TREE_STYLE_SHEET)
        # Selection, not the current item: focus alone (a neighbouring pane
        # hiding, say) makes the first item current without selecting it,
        # and must not start a web view.
        self._contents_tree.itemSelectionChanged.connect(self._show_current)

        self._pages = QtWidgets.QStackedWidget(splitter)
        self._pick_hint = QtWidgets.QLabel(PICK_SIMULATION_HINT, self._pages)
        self._pick_hint.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._pick_hint.setWordWrap(True)
        self._pages.addWidget(self._pick_hint)

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
        # The first show has the catalog read the tutorial pages, which fills
        # the contents.
        if event.new:
            self.model.active = True

        self._show_current()

    def _fill_contents(self):
        """Rebuild the tree, keep the pages of the tutorials still listed,
        and keep the picked simulation if it stays."""
        tree = self._contents_tree
        pages = self._pages
        records = list(self.model.tutorials)

        shown_page = pages.currentWidget()
        shown_item = self._picked_item()
        shown_record = getattr(shown_page, "record", None)
        shown_simulation = shown_item.text(0) if shown_item else None

        for record in list(self._pages_by_record):
            if record not in records:
                page = self._pages_by_record.pop(record)
                pages.removeWidget(page)
                page.retire()

        tree.blockSignals(True)
        tree.clear()

        heading_font = QtGui.QFont(tree.font())
        heading_font.setBold(True)

        # A font sized in pixels reports -1 points; leave its size alone.
        if heading_font.pointSizeF() > 0:
            heading_font.setPointSizeF(
                heading_font.pointSizeF() + HEADING_POINT_SIZE_INCREASE
            )

        selected = None

        for record in records:
            if record not in self._pages_by_record:
                self._pages_by_record[record] = TutorialSimulationsPage(record, pages)
                pages.addWidget(self._pages_by_record[record])

            tutorial_item = QtWidgets.QTreeWidgetItem(tree, [record.label])
            tutorial_item.setFont(0, heading_font)
            tutorial_item.setToolTip(0, record.tutorial.title)

            for simulation in record.simulations:
                item = QtWidgets.QTreeWidgetItem(tutorial_item, [simulation.title])
                item.setToolTip(0, f"{simulation.title} ({record.tutorial.title})")

                if record is shown_record and simulation.title == shown_simulation:
                    selected = item

        self._tree_records = records
        tree.expandAll()
        tree.blockSignals(False)

        # Nothing is picked for the user: a picked simulation starts a web view.
        if selected is not None:
            tree.setCurrentItem(selected)
        else:
            pages.setCurrentWidget(self._pick_hint)

    def _show_current(self, *args):
        """Show the picked simulation; a tutorial keeps its last one shown."""
        if self._contents_tree is None:
            return

        item = self._picked_item()

        if item is None:
            return

        tutorial_item = item.parent() if item.parent() is not None else item
        record = self._tree_records[
            self._contents_tree.indexOfTopLevelItem(tutorial_item)
        ]
        page = self._pages_by_record[record]

        self._pages.setCurrentWidget(page)

        if item is not tutorial_item:
            page.select_simulation(tutorial_item.indexOfChild(item))

        if self.visible:
            page.load()

    def _picked_item(self):
        """The tree item the user picked, or None."""
        items = self._contents_tree.selectedItems()

        return items[0] if items else None
