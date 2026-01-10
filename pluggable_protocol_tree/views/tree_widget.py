from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeView, QMenu, QPushButton
from PySide6.QtCore import Qt, QThread

from ..execution.runner import ProtocolRunnerWorker
from ..models.qt_tree import MvcTreeModel, ProtocolGridDelegate
from ..models.row import ActionRow, GroupRow

from enum import Enum


class RowType(Enum):
    step = "step"
    group = "group"


class ProtocolEditorWidget(QWidget):
    """
    A standalone Qt Widget for editing protocols.
    Can be embedded in a QMainWindow, QDialog, or Envisage DockPane.
    """

    def __init__(self, parent=None, columns=None):
        super().__init__(parent)

        self.columns = columns or []
        self.root_node = GroupRow(name="Root")

        # UI Setup
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeView()
        self._layout.addWidget(self.tree)

        self.model = MvcTreeModel(self.root_node, self.columns)
        self.tree.setModel(self.model)

        # Connect signals
        self.model.new_node_added.connect(self.on_node_added)

        # Delegate needs the widget (self) or tree as parent to manage editor lifecycles
        self.delegate = ProtocolGridDelegate(self.columns, self.tree)
        self.tree.setItemDelegate(self.delegate)

        # Context Menu
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.open_menu)

        # Add Run Controls
        self.btn_run = QPushButton("Run")
        self.btn_run.clicked.connect(self.start_execution)
        self._layout.addWidget(self.btn_run)  # Add to layout

        # Thread management
        self._thread = None
        self._worker = None

    def start_execution(self):
        """Initialize and start the runner thread."""
        self.btn_run.setEnabled(False)

        # 1. Create Thread and Worker
        self._thread = QThread()
        self._worker = ProtocolRunnerWorker(self.root_node, self.columns)
        self._worker.moveToThread(self._thread)

        # 2. Connect Thread Signals
        self._thread.started.connect(self._worker.run)
        self._worker.protocol_finished.connect(self._thread.quit)
        self._worker.protocol_finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        # 3. Connect UI Updates
        self._worker.step_started.connect(self.on_step_started)
        self._worker.protocol_finished.connect(self.on_run_finished)

        # 4. Start
        self._thread.start()

    def on_step_started(self, row_node):
        """Called from worker thread signal."""
        # Update model to highlight this row
        self.model.set_active_node(row_node)

    def on_run_finished(self):
        self.model.set_active_node(None)
        self.btn_run.setEnabled(True)

    def on_node_added(self, index):
        """Auto-expand groups when created so users see the child arrow."""
        self.tree.expand(index)
        self.tree.setCurrentIndex(index)

    def add_node(self, pos, row_type: RowType):
        index = self.tree.indexAt(pos)

        node = ActionRow() if row_type == RowType.step else GroupRow(name="Group")

        self.model.add_node(index, node)

    def open_menu(self, pos):
        menu = QMenu()
        index = self.tree.indexAt(pos)

        # Add actions
        menu.addAction("Add Step", lambda: self.add_node(pos, RowType.step))

        menu.addAction(
            "Add Group",
            lambda: self.model.add_node(index, GroupRow(name="Group")),
        )

        # Show menu
        menu.exec(self.tree.viewport().mapToGlobal(pos))
