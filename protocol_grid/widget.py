from collections import OrderedDict

import json
import dramatiq
# import h5py
from PySide6.QtWidgets import (QTreeView, QVBoxLayout, QWidget,
                               QPushButton, QHBoxLayout,QFileDialog, 
                               QDialog, QDialogButtonBox, QCheckBox,
                               QMenu)
from PySide6.QtCore import Qt
from PySide6.QtGui import (QStandardItemModel, QAction, 
                           QKeySequence, QShortcut)
from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from protocol_grid.model.tree_data import ProtocolGroup, ProtocolStep
from protocol_grid.model.protocol_visualization_helpers import (visualize_protocol_from_model, 
                                                   save_protocol_sequence_to_json,
                                                   visualize_protocol_with_swimlanes)
from protocol_grid.consts import (protocol_grid_fields,
                                  step_defaults, group_defaults, 
                                  GROUP_TYPE, STEP_TYPE, ROW_TYPE_ROLE) 
from protocol_grid.protocol_grid_helpers import (make_row, SpinBoxDelegate,
                                                 int_to_letters)

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
        QShortcut(QKeySequence(Qt.CTRL | Qt.Key_V), self, self.paste_below_selected)
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
        repetition_delegate = SpinBoxDelegate(self, integer=True)
        duration_delegate = SpinBoxDelegate(self, integer=False)
        voltage_delegate = SpinBoxDelegate(self, integer=False)
        frequency_delegate = SpinBoxDelegate(self, integer=False)

        self.tree.setItemDelegateForColumn(2, repetition_delegate)
        self.tree.setItemDelegateForColumn(3, duration_delegate)
        self.tree.setItemDelegateForColumn(4, voltage_delegate)
        self.tree.setItemDelegateForColumn(5, frequency_delegate)

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
        index = self.tree.indexAt(pos)
        if not index.isValid():
            return
        menu = QMenu(self)
        actions = [
            ("Delete", self.delete_selected),
            ("Insert Step Below", self.insert_below_selected),
            ("Copy", self.copy_selected),
            ("Cut", self.cut_selected),
            ("Paste Below", self.paste_below_selected),
            ("Undo", self.undo_last),
            ("Redo", self.redo_last),
        ]
        for name, slot in actions:
            action = QAction(name, self)
            action.triggered.connect(slot)
            menu.addAction(action)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def show_column_toggle_dialog(self, pos):
        dialog = QDialog(self)
        dialog.setWindowTitle("Options")
        layout = QVBoxLayout(dialog)
        checkboxes = []
        column_indices = []
        header = self.tree.header()

        for i, field in enumerate(protocol_grid_fields):
            if field in ("Description", "ID"):

                continue
            cb = QCheckBox(field)
            cb.setChecked(not self.tree.isColumnHidden(i))
            layout.addWidget(cb)
            checkboxes.append(cb)
            column_indices.append(i)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(button_box)

        def apply_changes():
            for cb, i in zip(checkboxes, column_indices):
                self.tree.setColumnHidden(i, not cb.isChecked())
            dialog.accept()
        
        button_box.accepted.connect(apply_changes)
        button_box.rejected.connect(dialog.reject)

        dialog.exec()

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

    def get_selected_rows(self):
        """
        Return list of (parent, row) for each unique row with at least one selected cell.
        Sorted in reverse order so that row indices remain valid when removing.
        """
        selected_indexes = self.tree.selectionModel().selectedIndexes()
        seen = set()
        row_refs = []
        for index in selected_indexes:
            item = self.model.itemFromIndex(index)
            parent = item.parent() or self.model.invisibleRootItem()
            row = item.row()
            key = (id(parent), row)
            if key not in seen:
                seen.add(key)
                row_refs.append((parent, row))
        row_refs.sort(key=lambda pr: (id(pr[0]), -pr[1])) 
        # descending order used because normal way would cause issues when removing scattered rows
        return row_refs
    
    def copy_selected(self):
        row_refs = self.get_selected_rows()
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

    def paste_below_selected(self):
        self.snapshot_for_undo()
        if not hasattr(self, '_copied_rows') or self._copied_rows is None:
            return
        row_refs = self.get_selected_rows()
        if not row_refs:
            return
        parent, row = row_refs[-1]
        for r, row_items in enumerate(self._copied_rows):
            parent.insertRow(row + 1 + r, [item.clone() for item in row_items])
        self.reassign_step_ids()

    def delete_selected(self):
        self.snapshot_for_undo()
        row_refs = self.get_selected_rows()
        if not row_refs:
            return
        for parent, row in row_refs:
            parent.removeRow(row)        
        self.reassign_step_ids()

    def insert_below_selected(self):
        """ Insert a new step before selected item """
        self.snapshot_for_undo()
        row_refs = self.get_selected_rows()
        if not row_refs:
            return   
        #TODO: implement remaining fields
        parent, row = row_refs[-1]  
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
        parent.insertRow(row + 1, step_items)
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

        #TODO: implement remaining fields
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

        #TODO: implement remaining fields
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
                    group_rep = parent_item.child(row, 2).text()
                    group_elements = parse_seq(desc_item)                    
                    sequence.append(
                        ProtocolGroup(
                            name=group_name,
                            elements=group_elements,
                            parameters={"Repetitions": int(group_rep)}
                        )
                    )
                elif row_type == STEP_TYPE:
                    try:
                        #TODO: implement remaining fields
                        parameters = {
                            "Repetitions": int(parent_item.child(row, 2).text()),
                            "Duration": float(parent_item.child(row, 3).text()),
                            "Voltage": float(parent_item.child(row, 4).text()),
                            "Frequency": float(parent_item.child(row, 5).text())
                        }
                    except Exception:
                        parameters = {}
                    sequence.append(ProtocolStep(name=desc_item.text(), parameters=parameters))
            return sequence

        root_item = self.model.invisibleRootItem()
        return parse_seq(root_item)

    def export_to_json(self):
        protocol_data = self.to_protocol_model()
        file_name, _ = QFileDialog.getSaveFileName(self, "Export Protocol as JSON", "protocol_export.json", "JSON Files (*.json)")
        if file_name:
            with open(file_name, 'w') as f:
                f.write(json.dumps([item.model_dump() for item in protocol_data], indent=4))
            save_protocol_sequence_to_json(protocol_data, file_name)
            logger.debug(f"Protocol exported to {file_name}")

    def export_to_png(self):
        protocol_data = self.to_protocol_model()
        file_name, _ = QFileDialog.getSaveFileName(self, "Export Protocol as PNG", "protocol_grid_ui_export.png", "PNG Files (*.png)")
        if file_name:
            # visualize_protocol_from_model(protocol_data, file_name.replace(".png", ""))
            visualize_protocol_with_swimlanes(protocol_data, file_name.replace(".png", ""), 5)
            logger.debug(f"Protocol PNG exported as {file_name}")

    def populate_treeview(self, protocol_sequence):
        self.clear_view()
        def add_seq(parent, seq):
            for obj in seq:
                if isinstance(obj, dict):
                    is_group = "elements" in obj
                else:
                    is_group = hasattr(obj, "elements")
                if is_group:
                    group_obj = obj if not isinstance(obj, dict) else ProtocolGroup(**obj)

                    group_name_val = getattr(group_obj, "name", "Group")
                    group_rep_val = (
                        str(getattr(group_obj, "parameters", {}).get("Repetitions", "1"))
                        if hasattr(group_obj, "parameters") else "1"
                    )

                    #TODO: implement remaining fields
                    group_items = make_row(
                        group_defaults,
                        overrides={
                            "Description": group_name_val,
                            "Repetitions": group_rep_val
                        },
                        row_type=GROUP_TYPE
                    )
                    parent.appendRow(group_items)
                    add_seq(group_items[0], group_obj.elements)
                else:
                    step_obj = obj if not isinstance(obj, dict) else ProtocolStep(**obj)

                    #TODO: implement remaining fields
                    step_items = make_row(
                        step_defaults,
                        overrides={
                            "Description": step_obj.name,
                            "ID": str(self.step_id),
                            "Repetitions": str(step_obj.parameters.get("Repetitions", "")),
                            "Duration": str(step_obj.parameters.get("Duration", "")),
                            "Voltage": str(step_obj.parameters.get("Voltage", "")),
                            "Frequency": str(step_obj.parameters.get("Frequency", "")),
                        },
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
                if "elements" in obj:
                    protocol_sequence.append(ProtocolGroup(**obj))
                else:
                    protocol_sequence.append(ProtocolStep(**obj))
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
