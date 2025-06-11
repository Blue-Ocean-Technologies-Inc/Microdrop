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


logger = get_logger(__name__, level="DEBUG")


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


class PGCWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tree = QTreeView()
        self.tree.setSelectionMode(QTreeView.SelectionMode.SingleSelection)

        # create Model
        self.model = QStandardItemModel()

        # set Model
        self.tree.setModel(self.model)

        # set Headers for columns
        self.model.setHorizontalHeaderLabels(["Description", "Repetitions", "Duration", "Voltage", "Frequency"])

        # Set delegates
        repetition_delegate = SpinBoxDelegate(self, integer=True)
        duration_delegate = SpinBoxDelegate(self, integer=False)
        voltage_delegate = SpinBoxDelegate(self, integer=False)
        frequency_delegate = SpinBoxDelegate(self, integer=False)

        self.tree.setItemDelegateForColumn(1, repetition_delegate)
        self.tree.setItemDelegateForColumn(2, duration_delegate)
        self.tree.setItemDelegateForColumn(3, voltage_delegate)
        self.tree.setItemDelegateForColumn(4, frequency_delegate)

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

        export_layout = QHBoxLayout()
        export_layout.addWidget(self.export_json_button)
        export_layout.addWidget(self.export_png_button)
        export_layout.addWidget(self.import_json_button)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.tree)
        self.layout.addLayout(button_layout)
        self.layout.addLayout(export_layout)
        self.setLayout(self.layout)

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
            if into and selected_item.get_item_type() == "Description" and selected_item.get_item_data() == "Group":
                parent_item = selected_item
            else:
                parent_item = selected_item.parent() or self.model.invisibleRootItem()

        group_name = PGCItem(item_type="Description", item_data="Group")
        group_rep = PGCItem(item_type="Repetitions", item_data="1")
        group_dur = PGCItem(item_type="Duration", item_data="")
        group_voltage = PGCItem(item_type="Voltage", item_data="")
        group_frequency = PGCItem(item_type="Frequency", item_data="")
        group = [group_name, group_rep, group_dur, group_voltage, group_frequency]
        # make calculate order function
        for group_member in group:
            if group_member.get_item_type() in ["Repetitions", "Description"]:
                group_member.setEditable(True)
            else:
                group_member.setEditable(False)
        parent_item.appendRow(group)
        self.tree.expandAll()

    def add_step(self, into=False):
        selected_indexes = self.tree.selectionModel().selectedIndexes()
        parent_item = self.model.invisibleRootItem()
        if selected_indexes:
            selected_index = selected_indexes[0]
            selected_item = self.model.itemFromIndex(selected_index)
            if into and selected_item.get_item_type() == "Description" and selected_item.get_item_data() == "Group":
                parent_item = selected_item
            else:
                parent_item = selected_item.parent() or self.model.invisibleRootItem()

        step_index = parent_item.rowCount() + 1
        step_name = PGCItem(item_type="Description", item_data=f"Step {step_index}")
        step_rep = PGCItem(item_type="Repetitions", item_data="1")
        step_dur = PGCItem(item_type="Duration", item_data="1.00")
        step_voltage = PGCItem(item_type="Voltage", item_data="0.00")
        step_frequency = PGCItem(item_type="Frequency", item_data="0.00")
        step = [step_name, step_rep, step_dur, step_voltage, step_frequency]

        for step_member in step:
            step_member.setEditable(True)
        parent_item.appendRow(step)
        self.tree.expandAll()

    def clear_view(self):
        self.model.clear()
        self.model.setHorizontalHeaderLabels(["Description", "Repetitions", "Duration", "Voltage", "Frequency"])

    def to_protocol_model(self):
        """
        Walks the QTreeView and builds a sequential list of ProtocolStep/ProtocolGroup.
        """
        def parse_seq(parent_item):
            sequence = []
            for row in range(parent_item.rowCount()):
                desc_item = parent_item.child(row, 0)
                # if desc_item is None or desc_item.get_item_type() != "Description":
                #     continue
                desc = desc_item.get_item_data()
                if desc == "Group" and parent_item.child(row, 0).hasChildren():
                    group_elements = parse_seq(desc_item)
                    sequence.append(ProtocolGroup(name="Group", elements=group_elements))
                else: # step
                    try:
                        parameters = {
                            "Repetitions": int(parent_item.child(row, 1).text()),
                            "Duration": float(parent_item.child(row, 2).text()),
                            "Voltage": float(parent_item.child(row, 3).text()),
                            "Frequency": float(parent_item.child(row, 4).text())
                        }
                    except Exception:
                        parameters = {}
                    sequence.append(ProtocolStep(name=desc, parameters=parameters))
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
                    group_item = PGCItem(item_type="Description", item_data="Group")
                    rep_item = PGCItem(item_type="Repetitions", item_data="1")
                    dur_item = PGCItem(item_type="Duration", item_data="")
                    volt_item = PGCItem(item_type="Voltage", item_data="")
                    freq_item = PGCItem(item_type="Frequency", item_data="")
                    group_row = [group_item, rep_item, dur_item, volt_item, freq_item]
                    parent.appendRow(group_row)
                    add_seq(group_item, group_obj.elements)
                else:
                    step_obj = obj if not isinstance(obj, dict) else ProtocolStep(**obj)
                    step_row = [
                        PGCItem(item_type="Description", item_data=step_obj.name),
                        PGCItem(item_type="Repetitions", item_data=str(step_obj.parameters.get("Repetitions", ""))),
                        PGCItem(item_type="Duration", item_data=str(step_obj.parameters.get("Duration", ""))),
                        PGCItem(item_type="Voltage", item_data=str(step_obj.parameters.get("Voltage", ""))),
                        PGCItem(item_type="Frequency", item_data=str(step_obj.parameters.get("Frequency", ""))),
                    ]
                    parent.appendRow(step_row)
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
