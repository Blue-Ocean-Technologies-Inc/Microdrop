import sys
import copy
import json
from PySide6.QtWidgets import (QTreeView, QVBoxLayout, QWidget, QHeaderView, QHBoxLayout,
                               QFileDialog, QMessageBox, QApplication, QMainWindow, QPushButton)
from PySide6.QtCore import Qt, QItemSelectionModel, QTimer, Signal
from PySide6.QtGui import QStandardItemModel, QKeySequence, QShortcut

from protocol_grid.protocol_grid_helpers import (make_row, ProtocolGridDelegate, 
                                               calculate_group_aggregation_from_children)
from protocol_grid.state.protocol_state import ProtocolState, ProtocolStep, ProtocolGroup
from protocol_grid.protocol_state_helpers import make_test_steps
from protocol_grid.consts import (GROUP_TYPE, STEP_TYPE, ROW_TYPE_ROLE, step_defaults, 
                                group_defaults, protocol_grid_fields)
from protocol_grid.extra_ui_elements import EditContextMenu, ColumnToggleDialog

protocol_grid_column_widths = [
    120, 70, 70, 70, 70, 70, 70, 100, 70, 70, 50, 110, 60, 90, 110, 90
]


class PGCWidget(QWidget):
    
    protocolChanged = Signal()
    
    def __init__(self, parent=None, state=None):
        super().__init__(parent)
        
        self.state = state or ProtocolState()
        
        self._column_visibility = {}
        self._column_widths = {}
        
        self.tree = QTreeView()
        self.model = QStandardItemModel()
        self.tree.setModel(self.model)
        self.delegate = ProtocolGridDelegate(self)
        self.tree.setItemDelegate(self.delegate)
        
        self.tree.setSelectionBehavior(QTreeView.SelectRows)
        self.tree.setSelectionMode(QTreeView.ExtendedSelection)
        
        self.create_buttons()
        
        layout = QVBoxLayout()
        layout.addWidget(self.tree)
        layout.addLayout(self.button_layout_1)  # Add/Insert buttons
        layout.addLayout(self.button_layout_2)  # Import/Export buttons
        self.setLayout(layout)
        
        self._programmatic_change = False
        self._block_aggregation = False
        self._sync_timer = QTimer()
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._delayed_sync)
        self._clipboard = []
        
        self.model.itemChanged.connect(self.on_item_changed)
        self.tree.selectionModel().selectionChanged.connect(self.on_selection_changed)
        
        self.setup_context_menu()
        self.setup_shortcuts()
        self.setup_header_context_menu()
        
        self.ensure_minimum_protocol()
        self.load_from_state()
        
    def create_buttons(self):
        self.button_layout_1 = QHBoxLayout()
        
        self.btn_add_step = QPushButton("Add Step")
        self.btn_add_step_into = QPushButton("Add Step Into")
        self.btn_add_group = QPushButton("Add Group")
        self.btn_add_group_into = QPushButton("Add Group Into")
        
        self.btn_add_step.clicked.connect(self.add_step)
        self.btn_add_step_into.clicked.connect(self.add_step_into)
        self.btn_add_group.clicked.connect(self.add_group)
        self.btn_add_group_into.clicked.connect(self.add_group_into)
        
        self.button_layout_1.addWidget(self.btn_add_step)
        self.button_layout_1.addWidget(self.btn_add_step_into)
        self.button_layout_1.addWidget(self.btn_add_group)
        self.button_layout_1.addWidget(self.btn_add_group_into)
        self.button_layout_1.addStretch()
        
        self.button_layout_2 = QHBoxLayout()
        
        self.btn_import = QPushButton("Import from JSON")
        self.btn_import_into = QPushButton("Import Into")
        self.btn_export = QPushButton("Export to JSON")
        
        self.btn_import.clicked.connect(self.import_from_json)
        self.btn_import_into.clicked.connect(self.import_into_json)
        self.btn_export.clicked.connect(self.export_to_json)
        
        self.button_layout_2.addWidget(self.btn_import)
        self.button_layout_2.addWidget(self.btn_import_into)
        self.button_layout_2.addWidget(self.btn_export)
        self.button_layout_2.addStretch()
        
    def setup_header_context_menu(self):
        header = self.tree.header()
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self.show_header_context_menu)
        
    def show_header_context_menu(self, pos):
        dialog = ColumnToggleDialog(self)
        dialog.exec()
        
    def on_selection_changed(self):
        selected_paths = self.get_selected_paths()
        
        has_selection = len(selected_paths) > 0
        self.btn_add_step_into.setEnabled(has_selection)
        self.btn_add_group_into.setEnabled(has_selection)
        self.btn_import_into.setEnabled(has_selection)
        
    def save_column_settings(self):
        for i, field in enumerate(protocol_grid_fields):
            self._column_visibility[field] = not self.tree.isColumnHidden(i)
            self._column_widths[field] = self.tree.header().sectionSize(i)
            
    def restore_column_settings(self):
        for i, field in enumerate(protocol_grid_fields):
            if field in self._column_visibility:
                self.tree.setColumnHidden(i, not self._column_visibility[field])
            if field in self._column_widths and self._column_widths[field] > 0:
                self.tree.setColumnWidth(i, self._column_widths[field])
        
    def ensure_minimum_protocol(self):
        if not self.state.sequence:
            default_step = ProtocolStep(
                parameters=dict(step_defaults),
                name="Step"
            )
            self.state.sequence.append(default_step)
            self.reassign_ids()
            
    def reassign_ids(self):
        def assign_ids_recursive(elements, parent_prefix=""):
            step_counter = 1
            group_counter = ord('A')
            
            for element in elements:
                if isinstance(element, ProtocolStep):
                    if parent_prefix:
                        element.parameters["ID"] = f"{parent_prefix}_{step_counter}"
                    else:
                        element.parameters["ID"] = str(step_counter)
                    step_counter += 1
                    
                elif isinstance(element, ProtocolGroup):
                    if parent_prefix:
                        group_id = f"{parent_prefix}_{chr(group_counter)}"
                    else:
                        group_id = chr(group_counter)
                    
                    element.parameters["ID"] = group_id
                    group_counter += 1
                    
                    assign_ids_recursive(element.elements, group_id)
                    
        assign_ids_recursive(self.state.sequence)
        
    def setup_context_menu(self):
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        
    def show_context_menu(self, pos):
        menu = EditContextMenu(self)
        global_pos = self.tree.mapToGlobal(pos)
        menu.exec(global_pos)
        
    def setup_shortcuts(self):
        shortcuts = [
            (QKeySequence.Delete, self.delete_selected),
            (QKeySequence("Ctrl+C"), self.copy_selected),
            (QKeySequence("Ctrl+X"), self.cut_selected),
            (QKeySequence("Ctrl+V"), self.paste_selected),
            (QKeySequence("Ctrl+Z"), self.undo_last),
            (QKeySequence("Ctrl+Y"), self.redo_last),
            (QKeySequence("Ctrl+Shift+Y"), self.redo_last),
            (QKeySequence("Ctrl+A"), self.select_all),
            (QKeySequence("Ctrl+D"), self.deselect_rows),
            (QKeySequence("Ctrl+I"), self.invert_row_selection),
            (QKeySequence("Insert"), self.insert_step),
            (QKeySequence("Ctrl+Insert"), self.insert_group),
            (QKeySequence("Ctrl+Shift+V"), self.paste_into),
        ]
        
        for key_seq, slot in shortcuts:
            shortcut = QShortcut(key_seq, self)
            shortcut.activated.connect(slot)
            
    def show_column_toggle_dialog(self):
        dialog = ColumnToggleDialog(self)
        dialog.exec()
        
    def _delayed_sync(self):
        """Delayed synchronization to avoid excessive updates."""
        if not self._programmatic_change:
            self.sync_to_state()
            
    def sync_to_state(self):
        """Immediately sync model to state."""
        if not self._programmatic_change:
            self.model_to_state()
            self.protocolChanged.emit()
            
    def model_to_state(self):
        self.state.sequence.clear()
        
        def convert_recursive(parent_item, target_list):
            for row in range(parent_item.rowCount()):
                desc_item = parent_item.child(row, 0)
                if not desc_item:
                    continue
                    
                row_type = desc_item.data(ROW_TYPE_ROLE)
                
                parameters = {}
                for col, field in enumerate(protocol_grid_fields):
                    item = parent_item.child(row, col)
                    if item:
                        if field == "Magnet":
                            checked = item.data(Qt.CheckStateRole) == 2 # == Qt.Checked
                            parameters[field] = "1" if checked else "0"
                        elif field == "Magnet Height":
                            last_value = item.data(Qt.UserRole + 2)
                            if last_value is not None and last_value != "":
                                parameters[field] = str(last_value)
                            else:   
                                parameters[field] = item.text()
                        elif field == "Video":
                            checked = item.data(Qt.CheckStateRole) == Qt.Checked
                            parameters[field] = "1" if checked else "0"
                        else:
                            parameters[field] = item.text()
                            
                if row_type == STEP_TYPE:
                    step = ProtocolStep(
                        parameters=parameters,
                        name=parameters.get("Description", "Step")
                    )
                    # Get device state from model
                    device_state = desc_item.data(Qt.UserRole + 100)
                    if device_state:
                        step.device_state = device_state
                    target_list.append(step)
                    
                elif row_type == GROUP_TYPE:
                    group = ProtocolGroup(
                        parameters=parameters,
                        name=parameters.get("Description", "Group")
                    )
                    # Recursively convert children
                    convert_recursive(desc_item, group.elements)
                    target_list.append(group)
                    
        convert_recursive(self.model.invisibleRootItem(), self.state.sequence)
        
    def save_selection(self):
        """Save current selection state."""
        selected_paths = self.get_selected_paths()
        return selected_paths
        
    def restore_selection(self, saved_paths):
        """Restore selection state."""
        if not saved_paths:
            return
            
        selection_model = self.tree.selectionModel()
        selection_model.clear()
        
        for path in saved_paths:
            index = self.model.index(path[0], 0)
            for row in path[1:]:
                if index.isValid():
                    index = self.model.index(row, 0, index)
                else:
                    break
                    
            if index.isValid():
                selection_model.select(index, QItemSelectionModel.Select | QItemSelectionModel.Rows)
        
    def load_from_state(self):
        saved_selection = self.save_selection()
        self.save_column_settings()        
        self._programmatic_change = True
        try:
            self.state_to_model()
            self.setup_headers()
            self.tree.expandAll()
            self.update_all_group_aggregations()
            self.update_step_dev_fields()
        finally:
            self._programmatic_change = False
            
        self.restore_column_settings()
        self.restore_selection(saved_selection)
            
    def state_to_model(self):
        self.model.clear()        
        self.model.setHorizontalHeaderLabels(protocol_grid_fields)
        
        def add_recursive(elements, parent_item):
            for element in elements:
                if isinstance(element, ProtocolStep):
                    row_items = make_row(step_defaults, element.parameters, STEP_TYPE)
                    row_items[0].setData(element.device_state, Qt.UserRole + 100)
                    parent_item.appendRow(row_items)                    
                elif isinstance(element, ProtocolGroup):
                    row_items = make_row(group_defaults, element.parameters, GROUP_TYPE)
                    parent_item.appendRow(row_items)
                    # Recursively add children
                    add_recursive(element.elements, row_items[0])
                    
        add_recursive(self.state.sequence, self.model.invisibleRootItem())
        self.setup_headers()
        
    def setup_headers(self):
        for i, width in enumerate(protocol_grid_column_widths):
            self.tree.setColumnWidth(i, width)
            
    def on_item_changed(self, item):
        if self._programmatic_change:
            return

        self.state.snapshot_for_undo()
        parent = item.parent() or self.model.invisibleRootItem()
        row = item.row()
        col = item.column()
        if col >= len(protocol_grid_fields):
            return

        field = protocol_grid_fields[col]

        if field == "Magnet":
            self._handle_magnet_change(parent, row)
            return

        desc_item = parent.child(row, 0)

        if desc_item and desc_item.data(ROW_TYPE_ROLE) == STEP_TYPE:
            self.update_single_step_dev_fields(desc_item)

        if field in ("Voltage", "Frequency", "Trail Length"):
            if desc_item and desc_item.data(ROW_TYPE_ROLE) == GROUP_TYPE:
                value = item.text()
                if value != "":
                    self._set_field_for_group(desc_item, field, value)
            if not self._block_aggregation:
                self._update_parent_aggregations(parent)

        if field in ("Duration", "Run Time"):
            self._update_parent_aggregations(parent)

        if field in ("Duration", "Repeat Duration", "Volume Threshold"):
            self._validate_numeric_field(item, field)

        if field in ("Trail Length", "Trail Overlay"):
            self._handle_trail_fields(parent, row)

        self.sync_to_state()
        
    def _set_field_for_group(self, group_item, field, value):
        """Recursively set a field for all steps and subgroups under a group, and set the group row's own value."""
        self._block_aggregation = True
        try:
            idx = protocol_grid_fields.index(field)
            parent_item = group_item.parent()
            if parent_item is None:
                parent_item = self.model.invisibleRootItem()
            group_row_item = parent_item.child(group_item.row(), idx)
            if group_row_item:
                group_row_item.setText(value)
            for row in range(group_item.rowCount()):
                desc_item = group_item.child(row, 0)
                if not desc_item:
                    continue
                row_type = desc_item.data(ROW_TYPE_ROLE)
                if row_type == STEP_TYPE:
                    item = group_item.child(row, idx)
                    if item:
                        item.setText(value)
                elif row_type == GROUP_TYPE:
                    self._set_field_for_group(desc_item, field, value)
        finally:
            self._block_aggregation = False
        
    def _handle_magnet_change(self, parent, row):
        magnet_col = protocol_grid_fields.index("Magnet")
        magnet_height_col = protocol_grid_fields.index("Magnet Height")
        magnet_item = parent.child(row, magnet_col)
        magnet_height_item = parent.child(row, magnet_height_col)
        if not magnet_item or not magnet_height_item:
            return

        raw_check_state = magnet_item.data(Qt.CheckStateRole)
        checked = raw_check_state == Qt.Checked or raw_check_state == 2

        if checked:
            last_value = magnet_height_item.data(Qt.UserRole + 2)
            if last_value is None or last_value == "":
                last_value = "0"
            magnet_height_item.setEditable(True)
            magnet_height_item.setText(str(last_value))
            self.model.dataChanged.emit(magnet_height_item.index(), magnet_height_item.index(), [Qt.EditRole])
        else:
            last_value = magnet_height_item.text()
            magnet_height_item.setData(last_value, Qt.UserRole + 2)
            magnet_height_item.setEditable(False)
            magnet_height_item.setText("")
            self.model.dataChanged.emit(magnet_height_item.index(), magnet_height_item.index(), [Qt.EditRole])

        self.model.itemChanged.emit(magnet_height_item)
            
    def _validate_numeric_field(self, item, field):
        """Validate numeric fields."""
        try:
            value = float(item.text())
            item.setText(f"{value:.1f}")
        except ValueError:
            item.setText("0.0")
            
    def _handle_trail_fields(self, parent, row):
        try:
            trail_length_col = protocol_grid_fields.index("Trail Length")
            overlay_col = protocol_grid_fields.index("Trail Overlay")
            
            trail_length_item = parent.child(row, trail_length_col)
            overlay_item = parent.child(row, overlay_col)
            
            if trail_length_item and overlay_item:
                trail_length = int(trail_length_item.text())
                max_overlay = max(0, trail_length - 1)
                overlay_val = int(overlay_item.text())
                
                if overlay_val > max_overlay:
                    overlay_item.setText(str(max_overlay))
        except (ValueError, IndexError):
            pass
            
    def _update_parent_aggregations(self, parent):
        current = parent
        while current and current != self.model.invisibleRootItem():
            if current.data(ROW_TYPE_ROLE) == GROUP_TYPE:
                row = current.row()
                parent_item = current.parent() or current.model().invisibleRootItem()
                group_items = [parent_item.child(row, c) for c in range(parent_item.columnCount())]
                children_rows = [
                    [current.child(r, c) for c in range(current.columnCount())]
                    for r in range(current.rowCount())
                ]
                calculate_group_aggregation_from_children(group_items, children_rows)
            current = current.parent()
            
    def update_single_step_dev_fields(self, desc_item):
        if not desc_item or desc_item.data(ROW_TYPE_ROLE) != STEP_TYPE:
            return
            
        parent = desc_item.parent() or self.model.invisibleRootItem()
        row = desc_item.row()
        
        try:
            repetitions_col = protocol_grid_fields.index("Repetitions")
            duration_col = protocol_grid_fields.index("Duration")
            repeat_duration_col = protocol_grid_fields.index("Repeat Duration")
            max_path_col = protocol_grid_fields.index("Max. Path Length")
            run_time_col = protocol_grid_fields.index("Run Time")
            
            repetitions_item = parent.child(row, repetitions_col)
            duration_item = parent.child(row, duration_col)
            repeat_duration_item = parent.child(row, repeat_duration_col)
            max_path_item = parent.child(row, max_path_col)
            run_time_item = parent.child(row, run_time_col)
            
            if not all([repetitions_item, duration_item, repeat_duration_item, max_path_item, run_time_item]):
                return
                
            device_state = desc_item.data(Qt.UserRole + 100)
            if not device_state:
                from protocol_grid.logic.device_state_manager import DeviceStateManager
                device_state = DeviceStateManager.create_default_device_state()
                desc_item.setData(device_state, Qt.UserRole + 100)
                
            repetitions = int(repetitions_item.text() or "1")
            duration = float(duration_item.text() or "1.0")
            repeat_duration = float(repeat_duration_item.text() or "1.0")
            
            max_path_length = device_state.longest_path_length()
            run_time = device_state.calculated_duration(duration, repetitions, repeat_duration)
            
            self._programmatic_change = True
            try:
                max_path_item.setText(str(max_path_length))
                run_time_item.setText(f"{run_time:.2f}")
            finally:
                self._programmatic_change = False
                
        except (ValueError, IndexError):
            pass
            
    def update_step_dev_fields(self):
        def update_recursive(parent):
            for row in range(parent.rowCount()):
                desc_item = parent.child(row, 0)
                if desc_item:
                    if desc_item.data(ROW_TYPE_ROLE) == STEP_TYPE:
                        self.update_single_step_dev_fields(desc_item)
                    elif desc_item.hasChildren():
                        update_recursive(desc_item)
                        
        update_recursive(self.model.invisibleRootItem())
        
    def update_all_group_aggregations(self):
        def update_recursive(parent):
            for row in range(parent.rowCount()):
                item = parent.child(row, 0)
                if item and item.data(ROW_TYPE_ROLE) == GROUP_TYPE:
                    group_items = [parent.child(row, c) for c in range(parent.columnCount())]
                    children_rows = [
                        [item.child(r, c) for c in range(item.columnCount())]
                        for r in range(item.rowCount())
                    ]
                    calculate_group_aggregation_from_children(group_items, children_rows)
                    if item.hasChildren():
                        update_recursive(item)
        update_recursive(self.model.invisibleRootItem())
        
    def get_selected_paths(self):
        paths = []
        selection = self.tree.selectionModel().selectedRows(0)
        for index in selection:
            path = []
            current = index
            while current.isValid():
                path.insert(0, current.row())
                current = current.parent()
            paths.append(path)
        return paths
        
    def get_item_by_path(self, path):
        item = self.model.invisibleRootItem()
        for row in path:
            if row < item.rowCount():
                item = item.child(row, 0)
            else:
                return None
        return item
        
    def _find_elements_by_path(self, path):
        elements = self.state.sequence
        for i in path:
            if i < len(elements):
                if isinstance(elements[i], ProtocolGroup):
                    elements = elements[i].elements
                else:
                    return elements
            else:
                return []
        return elements
        
    def select_all(self):
        self.tree.selectAll()
        
    def deselect_rows(self):
        self.tree.clearSelection()
        
    def invert_row_selection(self):
        selection_model = self.tree.selectionModel()
        all_indexes = []
        
        def collect_indexes(parent_index):
            for row in range(self.model.rowCount(parent_index)):
                index = self.model.index(row, 0, parent_index)
                all_indexes.append(index)
                if self.model.hasChildren(index):
                    collect_indexes(index)
                    
        collect_indexes(self.model.index(-1, -1))  # Root
        
        # Get currently selected rows
        selected_rows = set()
        for index in selection_model.selectedRows(0):
            selected_rows.add((index.row(), index.parent()))
            
        selection_model.clear()
        
        # Select all non-selected rows
        for index in all_indexes:
            if (index.row(), index.parent()) not in selected_rows:
                selection_model.select(index, QItemSelectionModel.Select | QItemSelectionModel.Rows)
                
    def insert_step(self):
        saved_selection = self.save_selection()
        
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            target_elements = self.state.sequence
            row = 0
        else:
            target_path = selected_paths[0]
            if len(target_path) == 1:
                target_elements = self.state.sequence
                row = target_path[0]
            else:
                parent_path = target_path[:-1]
                target_elements = self._find_elements_by_path(parent_path)
                row = target_path[-1]
                
        self.state.snapshot_for_undo()
        
        new_step = ProtocolStep(
            parameters=dict(step_defaults),
            name="Step"
        )
        target_elements.insert(row, new_step)
        
        self.reassign_ids()
        self.load_from_state()
        # self.sync_to_state()
        
        self.restore_selection(saved_selection)
        
    def insert_group(self):
        saved_selection = self.save_selection()
        
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            target_elements = self.state.sequence
            row = 0
        else:
            target_path = selected_paths[0]
            if len(target_path) == 1:
                target_elements = self.state.sequence
                row = target_path[0]
            else:
                parent_path = target_path[:-1]
                target_elements = self._find_elements_by_path(parent_path)
                row = target_path[-1]
                
        self.state.snapshot_for_undo()
        
        new_group = ProtocolGroup(
            parameters=dict(group_defaults),
            name="Group"
        )
        target_elements.insert(row, new_group)
        
        self.reassign_ids()
        self.load_from_state()
        # self.sync_to_state()
        
        self.restore_selection(saved_selection)
        
    def add_step(self):
        saved_selection = self.save_selection()
        
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            target_elements = self.state.sequence
            row = len(target_elements)
        else:
            target_path = selected_paths[0]
            target_item = self.get_item_by_path(target_path)
            if not target_item:
                return
            parent_path = target_path[:-1]
            target_elements = self._find_elements_by_path(parent_path)
            row = target_path[-1] + 1
                
        self.state.snapshot_for_undo()
        
        new_step = ProtocolStep(
            parameters=dict(step_defaults),
            name="Step"
        )
        target_elements.insert(row, new_step)
        
        self.reassign_ids()
        self.load_from_state()
        # self.sync_to_state()
        
        self.restore_selection(saved_selection)
        
    def add_step_into(self):
        saved_selection = self.save_selection()
        
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            return
            
        target_path = selected_paths[0]
        target_item = self.get_item_by_path(target_path)
        if not target_item:
            return
            
        self.state.snapshot_for_undo()
        
        new_step = ProtocolStep(
            parameters=dict(step_defaults),
            name="Step"
        )
        
        if target_item.data(ROW_TYPE_ROLE) == GROUP_TYPE:
            target_elements = self._find_elements_by_path(target_path)
            target_elements.append(new_step)
        else:
            parent_path = target_path[:-1]
            target_elements = self._find_elements_by_path(parent_path)
            row = target_path[-1] + 1
            target_elements.insert(row, new_step)
            
        self.reassign_ids()
        self.load_from_state()
        # self.sync_to_state()
        
        self.restore_selection(saved_selection)
        
    def add_group(self):
        saved_selection = self.save_selection()
        
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            target_elements = self.state.sequence
            row = len(target_elements)
        else:
            target_path = selected_paths[0]
            target_item = self.get_item_by_path(target_path)
            if not target_item:
                return
            parent_path = target_path[:-1]
            target_elements = self._find_elements_by_path(parent_path)
            row = target_path[-1] + 1
                
        self.state.snapshot_for_undo()
        
        new_group = ProtocolGroup(
            parameters=dict(group_defaults),
            name="Group"
        )
        target_elements.insert(row, new_group)
        
        self.reassign_ids()
        self.load_from_state()
        # self.sync_to_state()
        
        self.restore_selection(saved_selection)
        
    def add_group_into(self):
        saved_selection = self.save_selection()
        
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            return
            
        target_path = selected_paths[0]
        target_item = self.get_item_by_path(target_path)
        if not target_item:
            return
            
        self.state.snapshot_for_undo()
        
        new_group = ProtocolGroup(
            parameters=dict(group_defaults),
            name="Group"
        )
        
        if target_item.data(ROW_TYPE_ROLE) == GROUP_TYPE:
            target_elements = self._find_elements_by_path(target_path)
            target_elements.append(new_group)
        else:
            parent_path = target_path[:-1]
            target_elements = self._find_elements_by_path(parent_path)
            row = target_path[-1] + 1
            target_elements.insert(row, new_group)
            
        self.reassign_ids()
        self.load_from_state()
        # self.sync_to_state()
        
        self.restore_selection(saved_selection)
        
    def delete_selected(self):
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            return
            
        self.state.snapshot_for_undo()
        
        selected_paths.sort(reverse=True)
        
        for path in selected_paths:
            if len(path) == 1:
                if path[0] < len(self.state.sequence):
                    del self.state.sequence[path[0]]
            else:
                parent_path = path[:-1]
                elements = self._find_elements_by_path(parent_path)
                if path[-1] < len(elements):
                    del elements[path[-1]]
                    
        self.ensure_minimum_protocol()
        
        self.reassign_ids()
        self.load_from_state()
        # self.sync_to_state()
        
    def copy_selected(self):
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            return
        
        def is_descendant(path, other_path):
            return len(path) > len(other_path) and path[:len(other_path)] == other_path

        filtered_paths = []
        for path in selected_paths:
            is_child = False
            for i in selected_paths:
                if i != path and is_descendant(path, i):
                    is_child = True
                    break
            if not is_child:
                filtered_paths.append(path)
            
        copied_items = []
        for path in filtered_paths:
            if len(path) == 1:
                if path[0] < len(self.state.sequence):
                    copied_items.append(copy.deepcopy(self.state.sequence[path[0]]))
            else:
                parent_path = path[:-1]
                elements = self._find_elements_by_path(parent_path)
                if path[-1] < len(elements):
                    copied_items.append(copy.deepcopy(elements[path[-1]]))
                    
        self._clipboard = copied_items
        
    def cut_selected(self):
        self.copy_selected()
        self.delete_selected()
        
    def paste_selected(self, above=True):
        if not hasattr(self, '_clipboard') or not self._clipboard:
            return
            
        saved_selection = self.save_selection()
        
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            target_elements = self.state.sequence
            row = 0 if above else len(target_elements)
        else:
            target_path = selected_paths[0]
            if len(target_path) == 1:
                target_elements = self.state.sequence
                row = target_path[0] if above else target_path[0] + 1
            else:
                parent_path = target_path[:-1]
                target_elements = self._find_elements_by_path(parent_path)
                row = target_path[-1] if above else target_path[-1] + 1
                
        self.state.snapshot_for_undo()
        
        for i, item in enumerate(copy.deepcopy(self._clipboard)):
            target_elements.insert(row + i, item)
            
        self.reassign_ids()
        self.load_from_state()
        # self.sync_to_state()
        
        self.restore_selection(saved_selection)
        
    def paste(self):
        self.paste_selected(above=False)
        
    def paste_into(self):
        if not hasattr(self, '_clipboard') or not self._clipboard:
            return
            
        saved_selection = self.save_selection()
        
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            return
            
        target_path = selected_paths[0]
        target_item = self.get_item_by_path(target_path)
        if not target_item or target_item.data(ROW_TYPE_ROLE) != GROUP_TYPE:
            return
            
        target_elements = self._find_elements_by_path(target_path)
        
        self.state.snapshot_for_undo()
        
        for item in copy.deepcopy(self._clipboard):
            target_elements.append(item)
            
        self.reassign_ids()
        self.load_from_state()
        # self.sync_to_state()
        
        self.restore_selection(saved_selection)
        
    def undo_last(self):
        self._programmatic_change = True
        if self.state.undo_stack:
            self.state.undo()
            self.load_from_state()
        self._programmatic_change = False
            
    def redo_last(self):
        self._programmatic_change = True
        if self.state.redo_stack:
            self.state.redo()
            self.load_from_state()
        self._programmatic_change = False
            
    def undo(self):
        self.undo_last()
        
    def redo(self):
        self.redo_last()
        
    def export_to_json(self):        
        file_name, _ = QFileDialog.getSaveFileName(self, "Export Protocol to JSON", "", "JSON Files (*.json)")
        if file_name:
            flat_data = self.state.to_flat_export()
            with open(file_name, "w") as f:
                json.dump(flat_data, f, indent=2)
                
    def import_from_json(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Import Protocol from JSON", "", "JSON Files (*.json)")
        if file_name:
            try:
                with open(file_name, "r") as f:
                    data = json.load(f)
                    
                self.state.snapshot_for_undo()
                
                if "steps" in data and "fields" in data:
                    self.state.from_flat_export(data)
                else:
                    self.state.from_json(data)
                    
                self.state.undo_stack.clear()
                self.state.redo_stack.clear()
                
                self.reassign_ids()
                self.load_from_state()
                
            except Exception as e:
                QMessageBox.warning(self, "Import Error", f"Failed to import: {str(e)}")
                
    def import_into_json(self):
        saved_selection = self.save_selection()
        
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            return
            
        target_path = selected_paths[0]
        target_item = self.get_item_by_path(target_path)
        if target_item is None:
            return
            
        file_name, _ = QFileDialog.getOpenFileName(self, "Import Protocol from JSON", "", "JSON Files (*.json)")
        if not file_name:
            return
            
        try:
            with open(file_name, "r") as f:
                data = json.load(f)
                
            imported_state = ProtocolState()
            if "steps" in data and "fields" in data:
                imported_state.from_flat_export(data)
            else:
                imported_state.from_json(data)
                
            self.state.snapshot_for_undo()
            
            if target_item.data(ROW_TYPE_ROLE) == GROUP_TYPE:
                target_elements = self._find_elements_by_path(target_path)
                for obj in imported_state.sequence:
                    target_elements.append(copy.deepcopy(obj))
            else:
                parent_path = target_path[:-1]
                target_elements = self._find_elements_by_path(parent_path)
                row = target_path[-1] + 1
                for i, obj in enumerate(imported_state.sequence):
                    target_elements.insert(row + i, copy.deepcopy(obj))
                    
            self.reassign_ids()
            self.load_from_state()
            # self.sync_to_state()
            
            self.restore_selection(saved_selection)
            
        except Exception as e:
            QMessageBox.warning(self, "Import Error", f"Failed to import: {str(e)}")
            
    def assign_test_device_states(self):
        """Assign test device states to steps."""    
        test_steps = make_test_steps()
        test_states = [step.device_state for step in test_steps]
        
        def assign_recursive(elements):
            idx = 0
            for obj in elements:
                if isinstance(obj, ProtocolStep):
                    obj.device_state = copy.deepcopy(test_states[idx % len(test_states)])
                    idx += 1
                elif isinstance(obj, ProtocolGroup):
                    idx += assign_recursive(obj.elements)
            return idx
            
        self.state.snapshot_for_undo()
        assign_recursive(self.state.sequence)
        
        self.load_from_state()
        # self.sync_to_state()
        
    def open_device_editor(self):
        QMessageBox.information(self, "Device Editor", "Device state editor not yet implemented.")
        pass


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("Protocol Grid Widget")
    window.setGeometry(50, 50, 1400, 500)    
    widget = PGCWidget()
    window.setCentralWidget(widget)    
    window.show()    
    sys.exit(app.exec())