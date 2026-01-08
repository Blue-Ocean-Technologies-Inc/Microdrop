from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeView, QMenu
from PySide6.QtCore import Qt

from pluggable_protocol_tree.models.qt_tree import MvcTreeModel, ProtocolGridDelegate
from pluggable_protocol_tree.models.steps import GroupStep, ActionStep

from enum import Enum


class NodeType(Enum):
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
        self.root_step = GroupStep(name="Root")

        # UI Setup
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeView()
        self._layout.addWidget(self.tree)

        self.model = MvcTreeModel(self.root_step, self.columns)
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

    def add_node(self, pos, step_type: NodeType):
        index = self.tree.indexAt(pos)

        node = ActionStep() if step_type == NodeType.step else GroupStep(name="Group")

        self.model.add_node(index, node)

    def open_menu(self, pos):
        menu = QMenu()
        index = self.tree.indexAt(pos)

        # Add actions
        menu.addAction("Add Step", lambda: self.add_node(pos, NodeType.step))

        menu.addAction(
            "Add Group",
            lambda: self.model.add_node(index, GroupStep(name="Group")),
        )

        # Show menu
        menu.exec(self.tree.viewport().mapToGlobal(pos))
