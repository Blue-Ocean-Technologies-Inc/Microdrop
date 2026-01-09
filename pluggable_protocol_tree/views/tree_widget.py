from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeView, QMenu
from PySide6.QtCore import Qt

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
