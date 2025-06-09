from collections import OrderedDict

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
from protocol_grid.model.example_tree_data import visualize_protocol_from_model

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
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_group_button)
        button_layout.addWidget(self.add_group_into_button)
        button_layout.addWidget(self.add_step_button)
        button_layout.addWidget(self.add_step_into_button)

        export_layout = QHBoxLayout()
        export_layout.addWidget(self.export_json_button)
        export_layout.addWidget(self.export_png_button)

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

    def populate_treeview(self, protocol):
        self.clear_view()

        def add_items(parent, items):
            for key, value in items.items():
                if "Type" in value and value["Type"] == "Group":
                    group_item = PGCItem(item_type="Description", item_data=key)
                    rep_item = PGCItem(item_type="Repetitions", item_data=str(value.get("Repetitions", "")))
                    group_data = [group_item, rep_item, PGCItem(), PGCItem(), PGCItem()]
                    parent.appendRow(group_data)

                    # Add steps within the group
                    add_items(group_item, {k: v for k, v in value.items() if k not in ["Type", "Repetitions"]})
                else:
                    step_data = [
                        PGCItem(item_type="Description", item_data=key),
                        PGCItem(item_type="Repetitions", item_data="1"),
                        PGCItem(item_type="Duration", item_data=f'{value["Duration"]:.2f}'),
                        PGCItem(item_type="Voltage", item_data=f'{value["Voltage"]:.2f}'),
                        PGCItem(item_type="Frequency", item_data=f'{value["Frequency"]:.2f}')
                    ]
                    parent.appendRow(step_data)

        root_item = self.model.invisibleRootItem()
        add_items(root_item, protocol)
        self.tree.expandAll()

    def to_protocol_model(self):
        """
        Walk the QTreeView/QStandardItemModel and reconstruct ProtocolGroup/ProtocolStep tree.
        """
        def parse_group(item, idx_path=None):
            if idx_path is None:
                idx_path = [0]
            group_name = item.text() # group name is the header (column 0) of this item
            group = ProtocolGroup(
                group_idx=idx_path,
                name=group_name,
                elements=[]
            )
            for row in range(item.rowCount()):
                desc_item = item.child(row, 0)
                if desc_item is None or desc_item.get_item_type() != "Description":
                    continue
                desc = desc_item.get_item_data()
                # if the row is a group (has children)
                if desc == "Group" and desc_item.hasChildren():                   
                    group.elements.append(parse_group(desc_item, idx_path + [row]))  # recursion
                else:
                    parameters = {} # step (leaf)
                    try:
                        parameters["Repetitions"] = int(item.child(row, 1).text())
                        parameters["Duration"] = float(item.child(row, 2).text())
                        parameters["Voltage"] = float(item.child(row, 3).text())
                        parameters["Frequency"] = float(item.child(row, 4).text())
                    except Exception:
                        parameters = {}
                    step = ProtocolStep(
                        idx=idx_path + [row],
                        name=desc,
                        parameters=parameters
                    )
                    group.elements.append(step)
            return group

        root_item = self.model.invisibleRootItem()
        elements = []
        for row in range(root_item.rowCount()):
            desc_item = root_item.child(row, 0)
            if desc_item is None or desc_item.get_item_type() != "Description":
                continue
            desc = desc_item.get_item_data()
            if desc == "Group" and desc_item.hasChildren():
                elements.append(parse_group(desc_item, [row]))
            else:
                parameters = {}
                try:
                    parameters["Repetitions"] = int(root_item.child(row, 1).text())
                    parameters["Duration"] = float(root_item.child(row, 2).text())
                    parameters["Voltage"] = float(root_item.child(row, 3).text())
                    parameters["Frequency"] = float(root_item.child(row, 4).text())
                except Exception:
                    parameters = {}
                elements.append(ProtocolStep(
                    idx=[row],
                    name=desc,
                    parameters=parameters
                ))
        return ProtocolGroup(
            group_idx=[0],
            name="Root Group",
            elements=elements
        )

    def export_to_json(self):
        protocol_data = self.to_protocol_model()
        file_name, _ = QFileDialog.getSaveFileName(self, "Export Protocol as JSON", "protocol_export.json", "JSON Files (*.json)")
        if file_name:
            with open(file_name, 'w') as f:
                f.write(protocol_data.model_dump_json(indent=4))
            logger.debug(f"Protocol exported to {file_name}")

    def export_to_png(self):
        protocol_data = self.to_protocol_model()
        file_name, _ = QFileDialog.getSaveFileName(self, "Export Protocol as PNG", "protocol_grid_ui_export.png", "PNG Files (*.png)")
        if file_name:
            visualize_protocol_from_model(protocol_data, file_name.replace(".png", ""))
            logger.debug(f"Protocol PNG exported as {file_name}")


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
