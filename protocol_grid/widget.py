from collections import OrderedDict

import json
import dramatiq
# import h5py
from PySide6.QtWidgets import (QTreeView, QVBoxLayout, QWidget,
                               QPushButton, QHBoxLayout,QFileDialog)
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItemModel, QKeySequence, QShortcut
from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from protocol_grid.model.tree_data import ProtocolGroup, ProtocolStep
from protocol_grid.model.protocol_visualization_helpers import (visualize_protocol_from_model, 
                                                   save_protocol_sequence_to_json,
                                                   visualize_protocol_with_swimlanes)
from protocol_grid.consts import (protocol_grid_fields, step_defaults, group_defaults, 
                                  GROUP_TYPE, STEP_TYPE, ROW_TYPE_ROLE) 
from protocol_grid.protocol_grid_helpers import (make_row, ProtocolGridDelegate, 
                                                 get_selected_rows, invert_row_selection,
                                                 snapshot_for_undo, undo_last, redo_last,
                                                 reassign_step_ids, to_protocol_model, 
                                                 populate_treeview)
from protocol_grid.extra_ui_elements import ShowEditContextMenuAction, ShowColumnToggleDialogAction
from protocol_grid.state.protocol_state import ProtocolState
from protocol_grid.protocol_state_helpers import state_to_model, model_to_state, reassign_ids

logger = get_logger(__name__, level="DEBUG")


class PGCWidget(QWidget):
    def __init__(self, parent=None, state: ProtocolState=None):
        super().__init__(parent)
        self.state = state or ProtocolState()
        if not self.state.fields:
            self.state.fields = list(protocol_grid_fields)
        self.state.add_observer(self.load_from_state)

        # create Model
        self.model = QStandardItemModel()
        self.tree = QTreeView()
        # set Model
        self.tree.setModel(self.model)
        self.tree.setSelectionMode(QTreeView.SelectionMode.ExtendedSelection)
        self.tree.setSelectionBehavior(QTreeView.SelectionBehavior.SelectRows)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_edit_context_menu)

        QShortcut(QKeySequence(Qt.Key_Delete), self, self.delete_selected)
        QShortcut(QKeySequence(Qt.CTRL | Qt.Key_C), self, self.copy_selected)
        QShortcut(QKeySequence(Qt.CTRL | Qt.Key_X), self, self.cut_selected)
        QShortcut(QKeySequence(Qt.CTRL | Qt.SHIFT | Qt.Key_V), self, lambda: self.paste_selected(above=True))
        QShortcut(QKeySequence(Qt.CTRL | Qt.Key_V), self, lambda: self.paste_selected(above=False))
        QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Z), self, self.undo_last)
        QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Y), self, self.redo_last)

        header = self.tree.header()
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self.show_column_toggle_dialog) 

        # set Headers for columns
        self.model.setHorizontalHeaderLabels(protocol_grid_fields)
        initial_column_widths = [120, 30, 80, 80, 80, 80, 80, 80, 80, 30, 120]
        for i, width in enumerate(initial_column_widths):
            self.tree.setColumnWidth(i, width)

        # Set delegates
        self.delegate = ProtocolGridDelegate(self)
        self.tree.setItemDelegate(self.delegate)

        # Set edit trigger to single click
        self.tree.setEditTriggers(QTreeView.EditTrigger.CurrentChanged)

        # Group and Step creation buttons
        self.add_group_button = QPushButton("Add Group")
        self.add_group_into_button = QPushButton("Add Group Into")
        self.add_step_button = QPushButton("Add Step")
        self.add_step_into_button = QPushButton("Add Step Into")
        self.add_group_button.clicked.connect(lambda: self.add_group(into=False))        
        self.add_group_into_button.clicked.connect(lambda: self.add_group(into=True))        
        self.add_step_button.clicked.connect(lambda: self.add_step(into=False))        
        self.add_step_into_button.clicked.connect(lambda: self.add_step(into=True))

        self.export_json_button = QPushButton("Export to JSON")
        self.export_png_button = QPushButton("Export to PNG")
        self.import_json_button = QPushButton("Import from JSON")
        self.export_json_button.clicked.connect(self.export_to_json)        
        self.export_png_button.clicked.connect(self.export_to_png)        
        self.import_json_button.clicked.connect(self.import_from_json)
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_group_button)
        button_layout.addWidget(self.add_group_into_button)
        button_layout.addWidget(self.add_step_button)
        button_layout.addWidget(self.add_step_into_button)

        export_layout = QHBoxLayout()
        export_layout.addWidget(self.export_json_button)
        export_layout.addWidget(self.export_png_button)
        export_layout.addWidget(self.import_json_button)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.tree)
        self.layout.addLayout(button_layout)
        self.layout.addLayout(export_layout)
        self.setLayout(self.layout)

        self.action_show_edit_context_menu = ShowEditContextMenuAction(self)
        self.action_show_column_toggle_dialog = ShowColumnToggleDialogAction(self)

        self._copied_rows = None
        if not self.state.sequence:
            self.add_step(into=False)

    # ---------- State <-> Model sync ----------
    def load_from_state(self):
        state_to_model(self.state, self.model)
        reassign_ids(self.model)
        self.tree.expandAll()

    def save_to_state(self):
        model_to_state(self.model, self.state)
        reassign_ids(self.model)

    # ---------- UI Actions ----------
    def show_edit_context_menu(self, pos):
        self.action_show_edit_context_menu.perform(pos=pos)

    def show_column_toggle_dialog(self, pos):
        self.action_show_column_toggle_dialog.perform()

    def get_column_visibility(self):
        """
        Returns a list of bools showing which columns are visible.
        """
        return [not self.tree.isColumnHidden(i) for i in range(self.model.columnCount())]

    def set_column_visibility(self, visibility_list):
        for i, visible in enumerate(visibility_list):
            self.tree.setColumnHidden(i, not visible)

    def snapshot_for_undo(self):
        snapshot_for_undo(self.model, self.undo_stack, self.redo_stack) 

    def undo_last(self):
        self.state.undo()

    def redo_last(self):
        self.state.redo()

    def get_selected_rows(self, for_deletion=False):
        return get_selected_rows(self.tree, self.model, for_deletion)
    
    def select_all(self):
        self.tree.selectAll()
    
    def deselect_rows(self):
        self.tree.clearSelection()

    def invert_row_selection(self):
        invert_row_selection(self.tree, self.model)

    def copy_selected(self):
        row_refs = self.get_selected_rows()
        if not row_refs:
            self._copied_rows = None
            return
        self._copied_rows = []
        for parent, row in row_refs:
            items = [parent.child(row, col).clone() for col in range(self.model.columnCount())]
            def clone_children(src_item, tgt_item): # used recursively
                for i in range(src_item.rowCount()):
                    child_row = [src_item.child(i, c).clone() for c in range(self.model.columnCount())]
                    tgt_item.appendRow(child_row)
                    for c in range(self.model.columnCount()):
                        clone_children(src_item.child(i, c), tgt_item.child(i, c))
            for col, item in enumerate(items):
                clone_children(parent.child(row, col), item)
            self._copied_rows.append(items)

    def cut_selected(self):
        self.state.snapshot_for_undo()
        self.copy_selected()
        self.delete_selected()

    def paste_selected(self, above=True):
        self.state.snapshot_for_undo()
        if not self._copied_rows:
            return
        row_refs = self.get_selected_rows()
        if not row_refs:
            parent = self.model.invisibleRootItem()
            row = parent.rowCount()
        else:
            parent, row = row_refs[0]
        for r, items in enumerate(self._copied_rows):
            parent.insertRow(row + r if above else row + 1 + r, [item.clone() for item in items])
        self.save_to_state()
        reassign_ids(self.model)
        self.tree.expandAll()

    def delete_selected(self):
        self.state.snapshot_for_undo()
        row_refs = self.get_selected_rows(for_deletion=True)
        for parent, row in row_refs:
            parent.removeRow(row)
        self.save_to_state()
        reassign_ids(self.model)
        if self.model.invisibleRootItem().rowCount() == 0:
            self.add_step(into=False)

    def insert_step(self):
        self.state.snapshot_for_undo()
        row_refs = self.get_selected_rows()
        if not row_refs:
            parent = self.model.invisibleRootItem()
            row = parent.rowCount()
        else:
            parent, row = row_refs[0]
        step_number = 1
        step_items = make_row(step_defaults, overrides={"Description": f"Step", "ID": ""}, row_type=STEP_TYPE)
        parent.insertRow(row, step_items)
        self.save_to_state()
        reassign_ids(self.model)
        self.tree.expandAll()

    def insert_group(self):
        self.state.snapshot_for_undo()
        row_refs = self.get_selected_rows()
        if not row_refs:
            parent = self.model.invisibleRootItem()
            row = parent.rowCount()
        else:
            parent, row = row_refs[0]
        group_items = make_row(group_defaults, overrides={"Description": "Group"}, row_type=GROUP_TYPE)
        parent.insertRow(row, group_items)
        self.save_to_state()
        reassign_ids(self.model)
        self.tree.expandAll()

    def add_group(self, into=False):
        """
        Add a group to the tree view. If into is True, the group is added as a child of the selected item.
        Otherwise, the group is added as a sibling of the selected item.

        Removes necessity to deselect a direct child of root and setting focus on root to add a group as a
        sibling in the uppermost level.
        """
        self.state.snapshot_for_undo()
        sel = self.tree.selectedIndexes()
        parent = self.model.invisibleRootItem()
        if sel:
            selected = self.model.itemFromIndex(sel[0])
            if into and selected.data(ROW_TYPE_ROLE) == GROUP_TYPE:
                parent = selected
            else:
                parent = selected.parent() or self.model.invisibleRootItem()
        group_items = make_row(group_defaults, overrides={"Description": "Group"}, row_type=GROUP_TYPE)
        parent.appendRow(group_items)
        self.save_to_state()
        reassign_ids(self.model)
        self.tree.expandAll()

    def add_step(self, into=False):
        self.state.snapshot_for_undo()
        sel = self.tree.selectedIndexes()
        parent = self.model.invisibleRootItem()
        if sel:
            selected = self.model.itemFromIndex(sel[0])
            if into and selected.data(ROW_TYPE_ROLE) == GROUP_TYPE:
                parent = selected
            else:
                parent = selected.parent() or self.model.invisibleRootItem()
        step_items = make_row(step_defaults, overrides={"Description": f"Step", "ID": ""}, row_type=STEP_TYPE)
        parent.appendRow(step_items)
        self.save_to_state()
        reassign_ids(self.model)
        self.tree.expandAll()

    def export_to_json(self):
        self.save_to_state()
        protocol_data = self.state.to_json()
        file_name, _ = QFileDialog.getSaveFileName(self, "Export Protocol as JSON", "protocol_export.json", "JSON Files (*.json)")
        if file_name:
            with open(file_name, "w") as f:
                json.dump(protocol_data, f, indent=2)

    # ---------- Export to PNG under development (in ICEBOX) ----------
    def export_to_png(self):
        protocol_data = self.to_protocol_model()
        file_name, _ = QFileDialog.getSaveFileName(self, "Export Protocol as PNG", "protocol_grid_ui_export.png", "PNG Files (*.png)")
        if file_name:
            #TODO fix export as PNG with swim lanes
            # visualize_protocol_from_model(protocol_data, file_name.replace(".png", ""))
            visualize_protocol_with_swimlanes(protocol_data, file_name.replace(".png", ""), 5)
            logger.debug(f"Protocol PNG exported as {file_name}")

    def import_from_json(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Import Protocol from JSON", "", "JSON Files (*.json)")
        if file_name:
            with open(file_name, "r") as f:
                data = json.load(f)
            self.state.from_json(data)

from PySide6.QtWidgets import QApplication, QMainWindow
import sys

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Protocol Editor Demo")
        self.setCentralWidget(PGCWidget())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
