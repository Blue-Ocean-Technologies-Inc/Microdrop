from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTreeView,
    QMenu,
    QPushButton,
    QAbstractItemView,
)
from PySide6.QtCore import Qt, QPersistentModelIndex, QModelIndex, QThread, QObject

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

        # Store default flags to restore them later
        self._default_edit_triggers = self.tree.editTriggers()
        self._default_selection_mode = self.tree.selectionMode()

        ##################################################################################################
        # Protocol runner
        ##################################################################################################

        # --- THREADING SETUP ---
        # 1. Create the Worker and the Thread
        protocol_runner = ProtocolRunnerWorker(
            root_node=self.root_node, columns=self.columns
        )

        # 2. Define a QObject protocol runner Wrapper to use QThreads
        class QProtocolRunner(QObject):
            def __init__(self, runner, parent=None):
                super().__init__(parent)
                self.runner = runner

            # CRITICAL: This method belongs to the QObject that we move to the thread.
            # Calling this via Signal/Slot ensures it runs IN that thread.
            def start_worker(self):
                self.runner.start_protocol()

        # Instantiate and Move
        self.protocol_runner = QProtocolRunner(protocol_runner)
        self.worker_thread = QThread()
        self.protocol_runner.moveToThread(self.worker_thread)

        # Connect Thread Logic
        self.worker_thread.started.connect(self.protocol_runner.start_worker)

        # Connect cleanup
        self.protocol_runner.runner.qsignals.protocol_finished.connect(
            self.worker_thread.quit
        )

        # 5. Connect UI Updates
        # These signals come from the runner. qsignals is likely a QObject helper you made earlier.
        self.protocol_runner.runner.qsignals.step_started.connect(self.on_step_started)
        self.protocol_runner.runner.qsignals.protocol_finished.connect(
            self.on_run_finished
        )

        # Add Run Controls
        self.btn_run = QPushButton("Run")
        self.btn_run.clicked.connect(self.start_execution)
        self._layout.addWidget(self.btn_run)  # Add to layout

    def start_execution(self):
        self.btn_run.setEnabled(False)

        # --- 1. UI Updates (These will happen instantly now) ---
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.clearSelection()
        self.tree.setSelectionMode(QAbstractItemView.NoSelection)
        self.tree.setFocusPolicy(Qt.NoFocus)

        # --- 2. Optimization (Pre-calculate Map on Main Thread) ---
        self._node_map = {}
        self._cache_indices(self.model.index(0, 0))

        # --- 3. Start the Background Thread ---
        # This returns immediately, allowing the UI to process the
        # clearSelection() event above.
        self.worker_thread.start()

    def stop_execution(self):
        # Notify worker to stop (Cross-thread call is safe here because
        # your stop() implementation uses thread-safe locks/conditions)
        self.protocol_runner.runner.stop()

        # Wait for thread to actually exit
        self.worker_thread.quit()
        self.worker_thread.wait()

    def _cache_indices(self, parent_index):
        """Recursively maps every Node object to its QModelIndex."""
        rows = self.model.rowCount(parent_index)
        for r in range(rows):
            # Get index for column 0
            idx = self.model.index(r, 0, parent_index)
            node = idx.internalPointer()

            # Use PersistentIndex so it remains valid even if rows expand/collapse
            self._node_map[node] = QPersistentModelIndex(idx)

            # Recurse for children (Groups)
            if self.model.hasChildren(idx):
                self._cache_indices(idx)

    def on_step_started(self, row_node):
        """Called from worker thread signal. O(1) Lookup."""

        print("UI: Step Started")

        self.model.set_active_node(row_node)

    def on_run_finished(self):
        print("UI: Run finished")

        self.btn_run.setEnabled(True)
        self.model.set_active_node(None)

        # Restore Interaction
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.setEditTriggers(self._default_edit_triggers)
        self.tree.setSelectionMode(self._default_selection_mode)
        self.tree.setFocusPolicy(Qt.StrongFocus)

    ################################################################################################

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
