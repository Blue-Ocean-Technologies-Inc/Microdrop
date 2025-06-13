from collections import OrderedDict

import json
import dramatiq
# import h5py
from PySide6.QtWidgets import (QTreeView, QVBoxLayout, QWidget,
                               QPushButton, QHBoxLayout, QStyledItemDelegate, QSpinBox, QDoubleSpinBox,
                               QStyle, QSizePolicy, QFileDialog)
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItemModel, QStandardItem
from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from protocol_grid.model.tree_data import ProtocolGroup, ProtocolStep
from protocol_grid.model.protocol_visualization_helpers import (visualize_protocol_from_model, 
                                                   save_protocol_sequence_to_json,
                                                   visualize_protocol_with_swimlanes)
from protocol_grid.consts import (protocol_grid_fields,
                                  step_defaults,
                                  group_defaults) 

logger = get_logger(__name__, level="DEBUG")

GROUP_TYPE = "group"
STEP_TYPE = "step"
ROW_TYPE_ROLE = Qt.UserRole + 1

def make_row(defaults, overrides=None, row_type=None):
    """
    Create row (Step/Group) using default values defined in consts.py
    """
    overrides = overrides or {}
    items = []
    for i, field in enumerate(protocol_grid_fields):
        value = overrides.get(field, defaults.get(field, ""))
        item = PGCItem(item_type=field, item_data=value)
        if field == "Description" and row_type:
            item.setData(row_type, ROW_TYPE_ROLE)
        if field == "ID":
            item.setEditable(False)
        else:
            item.setEditable(True)
        items.append(item)
    return items


class SpinBoxDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, integer=True):
        super().__init__(parent)
        self.integer = integer

    def createEditor(self, parent, option, index):
        if self.integer:
            editor = QSpinBox(parent)
        else:
            editor = QDoubleSpinBox(parent)
            editor.setDecimals(2)
            editor.setSingleStep(0.01)
        editor.setMinimum(0)
        editor.setMaximum(10000)  # Set as per your requirement
        editor.installEventFilter(self)
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.ItemDataRole.EditRole)
        editor.setValue(int(value) if self.integer else float(value))

    def setModelData(self, editor, model, index):
        value = editor.value()
        model.setData(index, value, Qt.ItemDataRole.EditRole)


class PGCItem(QStandardItem):
    def __init__(self, item_type=None, item_data=None):
        super().__init__(item_data)
        self.item_type = item_type
        self.item_data = item_data

    def get_item_type(self):
        return self.item_type

    def get_item_data(self):
        return self.item_data

    def set_item_type(self, item_type):
        self.item_type = item_type

    def set_item_data(self, item_data):
        self.item_data = item_data

    def clone(self):
        new_item = PGCItem(self.item_type, self.item_data)
        new_item.setEditable(self.isEditable())
        for role in [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole]:
            new_item.setData(self.data(role), role)

        for row in range(self.rowCount()):
            # recursion
            child_row = [self.child(row, col).clone() for col in range(self.columnCount())]
            new_item.appendRow(child_row)
        return new_item


class PGCWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.step_id = 1
        #TODO: Implement Group IDs as alphabets
        self.group_id = 1

        self.tree = QTreeView()
        self.tree.setSelectionMode(QTreeView.SelectionMode.SingleSelection)
        self.tree.setSelectionBehavior(QTreeView.SelectionBehavior.SelectRows)

        # create Model
        self.model = QStandardItemModel()

        # set Model
        self.tree.setModel(self.model)

        # set Headers for columns
        self.model.setHorizontalHeaderLabels(protocol_grid_fields)

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
        self.add_group_button.clicked.connect(lambda: self.add_group(into=False))

        self.add_group_into_button = QPushButton("Add Group Into")
        self.add_group_into_button.clicked.connect(lambda: self.add_group(into=True))

        self.add_step_button = QPushButton("Add Step")
        self.add_step_button.clicked.connect(lambda: self.add_step(into=False))

        self.add_step_into_button = QPushButton("Add Step Into")
        self.add_step_into_button.clicked.connect(lambda: self.add_step(into=True))

        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self.delete_selected)

        self.insert_below_button = QPushButton("Insert Below")
        self.insert_below_button.clicked.connect(self.insert_below_selected)

        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(self.copy_selected)

        self.cut_button = QPushButton("Cut")
        self.cut_button.clicked.connect(self.cut_selected)

        self.paste_below_button = QPushButton("Paste Below")
        self.paste_below_button.clicked.connect(self.paste_below_selected)

        self.export_json_button = QPushButton("Export to JSON")
        self.export_json_button.clicked.connect(self.export_to_json)
        self.export_png_button = QPushButton("Export to PNG")
        self.export_png_button.clicked.connect(self.export_to_png)
        self.import_json_button = QPushButton("Import from JSON")
        self.import_json_button.clicked.connect(self.import_from_json)
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_group_button)
        button_layout.addWidget(self.add_group_into_button)
        button_layout.addWidget(self.add_step_button)
        button_layout.addWidget(self.add_step_into_button)

        edit_layout = QHBoxLayout()
        edit_layout.addWidget(self.delete_button)
        edit_layout.addWidget(self.insert_below_button)
        edit_layout.addWidget(self.copy_button)
        edit_layout.addWidget(self.cut_button)
        edit_layout.addWidget(self.paste_below_button)

        export_layout = QHBoxLayout()
        export_layout.addWidget(self.export_json_button)
        export_layout.addWidget(self.export_png_button)
        export_layout.addWidget(self.import_json_button)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.tree)
        self.layout.addLayout(button_layout)
        self.layout.addLayout(edit_layout)
        self.layout.addLayout(export_layout)
        self.setLayout(self.layout)

        if self.model.invisibleRootItem().rowCount() == 0:
            self.add_step(into=False)

    def get_selected_row(self):
        """
        Return parent item and row index of selected row, 
        or (None, None) if nothing is selected.
        """
        selected_indexes = self.tree.selectionModel().selectedIndexes()
        if not selected_indexes:
            return None, None
        selected_index = selected_indexes[0]
        item = self.model.itemFromIndex(selected_index)
        parent = item.parent() or self.model.invisibleRootItem()
        row = item.row()
        return parent, row
    
    def copy_selected(self):
        parent, row = self.get_selected_row()
        if parent is None:
            self._copied_row = None
            return
        # uses custom .clone() from PGCItem class
        items = [parent.child(row, col).clone() for col in range(self.model.columnCount())]
        self._copied_row = items

    def cut_selected(self):
        self.copy_selected()
        self.delete_selected()

    def paste_below_selected(self):
        if not hasattr(self, '_copied_row') or self._copied_row is None:
            return
        parent, row = self.get_selected_row()
        if parent is None:
            return
        new_items = [item.clone() for item in self._copied_row]
        parent.insertRow(row + 1, new_items)
        self.reassign_step_ids()

    def delete_selected(self):
        parent, row = self.get_selected_row()
        if parent is not None:
            parent.removeRow(row)
            self.reassign_step_ids()

    def insert_below_selected(self):
        """ Insert a new step before selected item """
        parent, row = self.get_selected_row()
        if parent is None:
            return
        
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
        parent.insertRow(row + 1, step_items)
        self.reassign_step_ids()
                
    def reassign_step_ids(self):
        """
        Reassign step IDs. (groups have no IDs for now)
        """ 
        self.step_id = 1
        def assign(parent):
            for row in range(parent.rowCount()):
                desc_item = parent.child(row, 0)
                id_item = parent.child(row, 1)
                if "Step" in desc_item.get_item_data(): # assuming step names contain "Step" for now
                    id_item.setText(str(self.step_id))
                    self.step_id += 1
                else: # group
                    id_item.setText("")
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
        self.tree.expandAll()

    def add_step(self, into=False):
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
            self.populate_treeview(protocol_sequence)

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
