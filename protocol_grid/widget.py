from collections import OrderedDict

import json
import dramatiq
# import h5py
from PySide6.QtWidgets import (QTreeView, QVBoxLayout, QWidget,
                               QPushButton, QHBoxLayout,QFileDialog)
from PySide6.QtCore import Qt, QItemSelectionModel
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
                                                 int_to_letters)
from protocol_grid.extra_ui_elements import edit_context_menu, column_toggle_dialog

logger = get_logger(__name__, level="DEBUG")


class PGCWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.step_id = 1
        self.group_id = 1

        self.undo_stack = []
        self.redo_stack = []

        self.tree = QTreeView()
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

        # create Model
        self.model = QStandardItemModel()

        # set Model
        self.tree.setModel(self.model)

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

        if self.model.invisibleRootItem().rowCount() == 0:
            self.add_step(into=False)

    def show_edit_context_menu(self, pos):
        edit_context_menu(self, pos)

    def show_column_toggle_dialog(self, pos):
        column_toggle_dialog(self, pos)

    def get_column_visibility(self):
        """
        Returns a list of bools showing which columns are visible.
        """
        return [not self.tree.isColumnHidden(i) for i in range(self.model.columnCount())]

    def set_column_visibility(self, visibility_list):
        for i, visible in enumerate(visibility_list):
            self.tree.setColumnHidden(i, not visible)

    def snapshot_for_undo(self):
        """
        Save a deep copy of the current model to the undo stack.
        """
        root_item = self.model.invisibleRootItem()
        clone = [
            [root_item.child(row, col).clone() for col in range(self.model.columnCount())] 
            for  row in range(root_item.rowCount())
        ]
        self.undo_stack.append(clone)
        if len(self.undo_stack) > 6: # limit stack size to 6
            self.undo_stack = self.undo_stack[-6:] 

        self.redo_stack.clear()  

    def undo_last(self):
        if not self.undo_stack:
            return
        
        current_state = [
            [self.model.invisibleRootItem().child(row, col).clone() 
            for col in range(self.model.columnCount())] 
            for row in range(self.model.invisibleRootItem().rowCount())
        ]
        self.redo_stack.append(current_state)

        last_state = self.undo_stack.pop()
        self.clear_view()
        for row_items in last_state:
            self.model.invisibleRootItem().appendRow([item.clone() for item in row_items])
        self.reassign_step_ids()
        self.tree.expandAll()

    def redo_last(self):
        if not self.redo_stack:
            return
        current_state = [
            [self.model.invisibleRootItem().child(row, col).clone() 
            for col in range(self.model.columnCount())] 
            for row in range(self.model.invisibleRootItem().rowCount())
        ]
        self.undo_stack.append(current_state)

        next_state = self.redo_stack.pop()
        self.clear_view()
        for row_items in next_state:
            self.model.invisibleRootItem().appendRow([item.clone() for item in row_items])
        self.reassign_step_ids()
        self.tree.expandAll()

    def get_selected_rows(self, for_deletion=False):
        """
        Returns list of (parent, row) for each unique row with at least one selected cell.
        - if for_deletion: sort by depth and descending row, for safe deletion.
        - else: preserve selection order (as returned by selectedRows(0)).
        """
        selection_model = self.tree.selectionModel()
        selected = selection_model.selectedRows(0)
        seen = set()
        row_refs = []
        for idx in selected:
            item = self.model.itemFromIndex(idx)
            parent = item.parent() or self.model.invisibleRootItem()
            row = item.row()
            key = (id(parent), row)
            if key not in seen:
                seen.add(key)
                row_refs.append((parent, row))
        if for_deletion:
            def get_depth(item):
                depth = 0 # depth needed for correct deletion order
                p = item.parent() or self.model.invisibleRootItem()
                while p != self.model.invisibleRootItem():
                    depth += 1
                    p = p.parent() or self.model.invisibleRootItem()
                return depth
            row_refs_with_depth = [((parent, row), get_depth(parent.child(row, 0))) for parent, row in row_refs]
            row_refs_with_depth.sort(key=lambda prd: (-prd[1], -prd[0][1]))  # deepest, then largest row index first
            return [pr for pr, _ in row_refs_with_depth]
        return row_refs
    
    def select_all(self):
        self.tree.selectAll()
    
    def deselect_rows(self):
        self.tree.clearSelection()

    def invert_row_selection(self):
        """
        Fix used: After the initial invert, for each group, 
        check if any of its children are selected.
        
        Step 1: Find selected groups and their children (to be inverted).
        Clear selection.

        Step 2: Select all rows not selected,
        except children of groups identified in step 1

        Step 3: Now go through each group, 
        select the group only if any of its children are selected.

        """
        model = self.model
        selection_model = self.tree.selectionModel()

        def collect_all_row_indexes(parent_item):
            indexes = []
            for row in range(parent_item.rowCount()):
                index = model.index(row, 0, parent_item.index())
                indexes.append(index)
                child_item = parent_item.child(row, 0)
                if child_item and child_item.hasChildren():
                    indexes.extend(collect_all_row_indexes(child_item))
            return indexes

        def collect_all_descendant_indexes(item):
            indexes = []
            for row in range(item.rowCount()):
                child = item.child(row, 0)
                indexes.append(child.index())
                if child.hasChildren():
                    indexes.extend(collect_all_descendant_indexes(child))
            return indexes

        root_item = model.invisibleRootItem()
        all_indexes = collect_all_row_indexes(root_item)
        old_selected_indexes = set(selection_model.selectedRows(0))

        # step 1
        selected_group_indexes = []
        selected_group_descendants = set()
        for idx in old_selected_indexes:
            item = model.itemFromIndex(idx)
            row_type = item.data(ROW_TYPE_ROLE)
            if row_type == GROUP_TYPE:
                selected_group_indexes.append(idx)
                selected_group_descendants.update(collect_all_descendant_indexes(item))
        selection_model.clearSelection()
        # step 2
        for idx in all_indexes:
            if idx in old_selected_indexes:
                continue 
            if idx in selected_group_descendants:
                continue 
            selection_model.select(idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)

        # step 3 (bottom-up approach: first process children, and then the group)
        # doing this because expected behaviour was not observed for certain cases involving subgroups.
        def fix_group_selection(item):
            for row in range(item.rowCount()):
                child = item.child(row, 0)
                fix_group_selection(child)
            if item.data(ROW_TYPE_ROLE) == GROUP_TYPE:
                group_idx = item.index()
                descendant_indexes = collect_all_descendant_indexes(item)
                any_child_selected = any(
                    selection_model.isRowSelected(idx.row(), idx.parent())
                    for idx in descendant_indexes
                )
                if any_child_selected:
                    selection_model.select(group_idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)
                else:
                    selection_model.select(group_idx, QItemSelectionModel.Deselect | QItemSelectionModel.Rows)
        
        fix_group_selection(root_item)

    def copy_selected(self):
        row_refs = self.get_selected_rows(for_deletion=False)
        if not row_refs:
            self._copied_rows = None
            return
        self._copied_rows = [
            [parent.child(row, col).clone() for col in range(self.model.columnCount())]
            for parent, row in row_refs
        ]

    def cut_selected(self):
        self.snapshot_for_undo()
        self.copy_selected()
        self.delete_selected()

    def paste_selected(self, above=True):
        self.snapshot_for_undo()
        if not hasattr(self, '_copied_rows') or self._copied_rows is None:
            return
        row_refs = self.get_selected_rows(for_deletion=False)
        if not row_refs:
            return
        parent, row = row_refs[0]
        if above:
            for r, row_items in enumerate(self._copied_rows):
                parent.insertRow(row + r, [item.clone() for item in row_items])
        else:
            for r, row_items in enumerate(self._copied_rows):
                parent.insertRow(row + 1 + r, [item.clone() for item in row_items])
        self.reassign_step_ids()

    def delete_selected(self):
        self.snapshot_for_undo()
        row_refs = self.get_selected_rows(for_deletion=True)
        if not row_refs:
            return
        for parent, row in row_refs:
            parent.removeRow(row)        
        self.reassign_step_ids()
        if self.model.invisibleRootItem().rowCount() == 0:
            self.add_step(into=False)

    def insert_step(self):
        """ Insert a new step before selected item """
        self.snapshot_for_undo()
        row_refs = self.get_selected_rows()
        if not row_refs:
            return   
        parent, row = row_refs[0]  
        step_number = self.step_id
        self.step_id += 1
        step_items = make_row(
            step_defaults,
            overrides={
                "Description": f"Step {step_number}",
                "ID": str(step_number)
            },
            row_type=STEP_TYPE
        )
        parent.insertRow(row, step_items)
        self.reassign_step_ids()

    def insert_group(self):
        """ Insert a new group before selected item """
        self.snapshot_for_undo()
        row_refs = self.get_selected_rows()
        if not row_refs:
            return   
        parent, row = row_refs[0]  
        group_items = make_row(
            group_defaults,
            overrides={"Description": "Group"},
            row_type=GROUP_TYPE
        )
        parent.insertRow(row, group_items)
        self.reassign_step_ids()
                
    def reassign_step_ids(self):
        """
        Reassign step IDs. (groups have no IDs for now)
        """ 
        self.step_id = 1
        self.group_id = 1
        def assign(parent):
            for row in range(parent.rowCount()):
                desc_item = parent.child(row, 0)
                id_item = parent.child(row, 1)
                row_type = desc_item.data(ROW_TYPE_ROLE)
                if row_type == STEP_TYPE:
                    id_item.setText(str(self.step_id))
                    self.step_id += 1
                elif row_type == GROUP_TYPE:
                    id_item.setText(int_to_letters(self.group_id))
                    self.group_id += 1
                if desc_item.hasChildren():
                    assign(desc_item)
        assign(self.model.invisibleRootItem())


    def add_group(self, into=False):
        """
        Add a group to the tree view. If into is True, the group is added as a child of the selected item.
        Otherwise, the group is added as a sibling of the selected item.

        Removes necessity to deselect a direct child of root and setting focus on root to add a group as a
        sibling in the uppermost level.
        """
        self.snapshot_for_undo() 
        # Get the selected items' indices
        selected_indexes = self.tree.selectionModel().selectedIndexes()

        # Set the parent item to the invisible root item
        parent_item = self.model.invisibleRootItem()

        # If there is are multiple selected items, make adjustment based on uppermost selected item
        if selected_indexes:
            selected_index = selected_indexes[0]
            selected_item = self.model.itemFromIndex(selected_index)
            # If Group
            if into and selected_item.data(ROW_TYPE_ROLE) == GROUP_TYPE:
                parent_item = selected_item
            else:
                parent_item = selected_item.parent() or self.model.invisibleRootItem()

        group_items = make_row(
            group_defaults,
            overrides={"Description": "Group"},
            row_type=GROUP_TYPE
        )
        parent_item.appendRow(group_items)
        self.reassign_step_ids()
        self.tree.expandAll()

    def add_step(self, into=False):
        self.snapshot_for_undo()
        selected_indexes = self.tree.selectionModel().selectedIndexes()
        parent_item = self.model.invisibleRootItem()
        if selected_indexes:
            selected_index = selected_indexes[0]
            selected_item = self.model.itemFromIndex(selected_index)
            if into and selected_item.data(ROW_TYPE_ROLE) == GROUP_TYPE:
                parent_item = selected_item
            else:
                parent_item = selected_item.parent() or self.model.invisibleRootItem()
        step_number = self.step_id
        self.step_id += 1
        step_items = make_row(
            step_defaults,
            overrides={
                "Description": f"Step {step_number}",
                "ID": str(step_number)
            },
            row_type=STEP_TYPE
        )
        parent_item.appendRow(step_items)
        self.reassign_step_ids()
        self.tree.expandAll()

    def clear_view(self):
        self.model.clear()
        self.model.setHorizontalHeaderLabels(protocol_grid_fields)
        self.step_id = 1
        self.group_id = 1
        
    def to_protocol_model(self):
        """
        Walks the QTreeView and builds a sequential list of ProtocolStep/ProtocolGroup.
        """
        def parse_seq(parent_item):
            sequence = []
            for row in range(parent_item.rowCount()):
                desc_item = parent_item.child(row, 0)
                row_type = desc_item.data(ROW_TYPE_ROLE)
                if row_type == GROUP_TYPE:
                    group_name = desc_item.text()
                    fields = {}
                    for i, field in enumerate(protocol_grid_fields):
                        item = parent_item.child(row, i)
                        if item:
                            value = item.text() if field != "Video" else (
                                1 if item.data(Qt.CheckStateRole) == Qt.Checked else 0
                            )
                            fields[field] = value
                    group_rep = fields.get("Repetitions", step_defaults["Repetitions"])
                    group_elements = parse_seq(desc_item)      
                    group_dict = {
                        "name": group_name,
                        "elements": [e for e in group_elements],
                        "parameters": {k: fields.get(k, step_defaults.get(k, "")) 
                                       for k in protocol_grid_fields if k not in (
                                           "Description", "ID", "elements", "name")
                        }
                    }              
                    sequence.append(group_dict)
                elif row_type == STEP_TYPE:
                    fields = {}
                    for i, field in enumerate(protocol_grid_fields):
                        item = parent_item.child(row, i)
                        if item:
                            value = item.text() if field != "Video" else (
                                1 if item.data(Qt.CheckStateRole) == Qt.Checked else 0
                            )
                            fields[field] = value
                    step_dict = {
                        "name": fields.get("Description", step_defaults["Description"]),
                        "parameters": {k: fields.get(k, step_defaults.get(k, "")) 
                                       for k in protocol_grid_fields if k not in (
                                           "Description", "ID", "elements", "name")
                        }
                    }
                    sequence.append(step_dict)
            return sequence

        root_item = self.model.invisibleRootItem()
        return parse_seq(root_item)

    def export_to_json(self):
        protocol_data = self.to_protocol_model()
        file_name, _ = QFileDialog.getSaveFileName(self, "Export Protocol as JSON", "protocol_export.json", "JSON Files (*.json)")
        if file_name:
           save_protocol_sequence_to_json(protocol_data, file_name)

    def export_to_png(self):
        protocol_data = self.to_protocol_model()
        file_name, _ = QFileDialog.getSaveFileName(self, "Export Protocol as PNG", "protocol_grid_ui_export.png", "PNG Files (*.png)")
        if file_name:
            #TODO fix export as PNG with swim lanes
            # visualize_protocol_from_model(protocol_data, file_name.replace(".png", ""))
            visualize_protocol_with_swimlanes(protocol_data, file_name.replace(".png", ""), 5)
            logger.debug(f"Protocol PNG exported as {file_name}")

    def populate_treeview(self, protocol_sequence):
        self.clear_view()
        def add_seq(parent, seq):
            for obj in seq:
                is_group = "elements" in obj
                if is_group:
                    group_obj = obj
                    group_name_val = group_obj.get("name", group_defaults["Description"])
                    group_params = group_obj.get("parameters", {})
                    group_data = {**group_defaults, **group_params, "Description": group_name_val}
                    for k in group_data:
                        if k == "Video":
                            try:
                                group_data[k] = int(group_data[k])
                            except Exception:
                                group_data[k] = 0
                        else:
                            group_data[k] = str(group_data[k]) if group_data[k] is not None else ""
                    group_items = make_row(
                        group_defaults,
                        overrides=group_data,
                        row_type=GROUP_TYPE
                    )
                    parent.appendRow(group_items)
                    add_seq(group_items[0], group_obj.get("elements", []))
                else:
                    step_obj = obj
                    step_name = step_obj.get("name", step_defaults["Description"])
                    step_params = step_obj.get("parameters", {})
                    step_data = {**step_defaults, **step_params, "Description": step_name}
                    for k in step_data:
                        if k == "Video":
                            try:
                                step_data[k] = int(step_data[k])
                            except Exception:
                                step_data[k] = 0
                        else:
                            step_data[k] = str(step_data[k]) if step_data[k] is not None else ""
                    step_items = make_row(
                        step_defaults,
                        overrides=step_data,
                        row_type=STEP_TYPE
                    )
                    self.step_id += 1
                    parent.appendRow(step_items)
        root_item = self.model.invisibleRootItem()
        add_seq(root_item, protocol_sequence)
        self.reassign_step_ids()
        self.tree.expandAll()

    def import_from_json(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Import Protocol from JSON", "", "JSON Files (*.json)")
        if file_name:
            with open(file_name, "r") as f:
                data = json.load(f)
            protocol_sequence = []
            for obj in data:
                protocol_sequence.append(obj)
            prev_visibility = self.get_column_visibility()
            self.populate_treeview(protocol_sequence)
            self.set_column_visibility(prev_visibility)

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
