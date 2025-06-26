import json
import dramatiq
# import h5py
from PySide6.QtWidgets import (QTreeView, QVBoxLayout, QWidget,
                               QPushButton, QHBoxLayout,QFileDialog,
                               QAbstractItemDelegate)
from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtGui import QStandardItemModel, QKeySequence, QShortcut
from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from protocol_grid.model.tree_data import ProtocolGroup, ProtocolStep
from protocol_grid.model.protocol_visualization_helpers import (visualize_protocol_from_model, 
                                                   visualize_protocol_with_swimlanes)
from protocol_grid.consts import (protocol_grid_fields, step_defaults, group_defaults, 
                                  GROUP_TYPE, STEP_TYPE, ROW_TYPE_ROLE) 
from protocol_grid.protocol_grid_helpers import (make_row, ProtocolGridDelegate, PGCItem, 
                                                 get_selected_rows, invert_row_selection)
from protocol_grid.extra_ui_elements import ShowEditContextMenuAction, ShowColumnToggleDialogAction
from protocol_grid.state.protocol_state import ProtocolState
from protocol_grid.protocol_state_helpers import state_to_model, model_to_state, reassign_ids, clamp_trail_overlay

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
        
        self._programmatic_change = False
        self.model.itemChanged.connect(self.on_item_changed)

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
        initial_column_widths = [120, 40, 80, 80, 80, 80, 60, 60, 80, 80, 80, 40, 80, 40, 80]
        for i, width in enumerate(initial_column_widths):
            self.tree.setColumnWidth(i, width)

        # Set delegates
        self.delegate = ProtocolGridDelegate(self)
        self.tree.setItemDelegate(self.delegate)

        # Set edit trigger to allow editing of all cells
        self.tree.setEditTriggers(QTreeView.EditTrigger.AllEditTriggers)

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
        # export_layout.addWidget(self.export_png_button)
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
        col_vis, col_widths = self.get_column_state()
        state_to_model(self.state, self.model)
        clamp_trail_overlay(self.model)
        reassign_ids(self.model)
        self.tree.expandAll()
        self.set_column_state(col_vis, col_widths)
        self.update_all_group_aggregations()

    def save_to_state(self):
        col_vis, col_widths = self.get_column_state()
        model_to_state(self.model, self.state)
        reassign_ids(self.model)
        self.set_column_state(col_vis, col_widths)

    def on_item_changed(self, item):
        if self._programmatic_change:
            return
        self.state.snapshot_for_undo()
        col = item.column()
        field = protocol_grid_fields[col]
        row = item.row()
        parent = item.parent() or self.model.invisibleRootItem()

        if field in ("Repeat Duration", "Repetitions", "Duration"):
            desc_item = parent.child(row, 0)
            if desc_item is not None and desc_item.data(ROW_TYPE_ROLE) == STEP_TYPE:
                rep_col = protocol_grid_fields.index("Repetitions")
                dur_col = protocol_grid_fields.index("Duration")
                repeat_dur_col = protocol_grid_fields.index("Repeat Duration")
                try:
                    repetitions = float(parent.child(row, rep_col).text())
                except Exception:
                    repetitions = 0
                try:
                    duration = float(parent.child(row, dur_col).text())
                except Exception:
                    duration = 0
                min_repeat_duration = repetitions * duration
                repeat_duration_item = parent.child(row, repeat_dur_col)
                try:
                    repeat_duration = float(repeat_duration_item.text())
                except Exception:
                    repeat_duration = 0
                if repeat_duration < min_repeat_duration:
                    self._programmatic_change = True
                    repeat_duration_item.setText(f"{min_repeat_duration:.2f}")
                    self._programmatic_change = False
            self.update_all_group_aggregations()

        if field == "Magnet":
            checked = bool(item.data(Qt.CheckStateRole))
            magnet_height_col = protocol_grid_fields.index("Magnet Height")
            magnet_height_item = parent.child(row, magnet_height_col)
            if magnet_height_item is not None:
                if not checked:
                    last_value = magnet_height_item.text()
                    magnet_height_item.setData(last_value, Qt.UserRole + 2)
                    magnet_height_item.setEditable(False)
                    magnet_height_item.setText("")
                else:
                    last_value = magnet_height_item.data(Qt.UserRole + 2)
                    if last_value is None or last_value == "":
                        last_value = "0"
                    magnet_height_item.setEditable(True)
                    magnet_height_item.setText(str(last_value))

        if field in ("Voltage", "Frequency", "Trail Length"):
            desc_item = parent.child(row, 0)
            if desc_item is not None and desc_item.data(ROW_TYPE_ROLE) == GROUP_TYPE and item == parent.child(row, col):
                new_value = item.text()
                if new_value != "":
                    def set_value_recursive(group_item):
                        for r in range(group_item.rowCount()):
                            child_desc = group_item.child(r, 0)
                            if child_desc is None:
                                continue
                            child_type = child_desc.data(ROW_TYPE_ROLE)
                            child_item = group_item.child(r, col)
                            if child_type == GROUP_TYPE:
                                if child_item is not None:
                                    self._programmatic_change = True
                                    child_item.setText(new_value)
                                    child_item.setEditable(True)
                                    self._programmatic_change = False
                                set_value_recursive(child_desc)
                            elif child_type == STEP_TYPE:
                                if child_item is not None:
                                    self._programmatic_change = True
                                    child_item.setText(new_value)
                                    self._programmatic_change = False
                    set_value_recursive(desc_item)
            self.update_all_group_aggregations()
        self.save_to_state()

    def update_all_group_aggregations(self):
        def update_group(group_item):
            if group_item.data(ROW_TYPE_ROLE) == GROUP_TYPE:
                if group_item.rowCount() == 0:
                    return
                for col, field in enumerate(protocol_grid_fields):
                    if field in ("Voltage", "Frequency", "Trail Length"):
                        values = set()
                        def collect_step_values(item):
                            for r in range(item.rowCount()):
                                child_desc = item.child(r, 0)
                                if child_desc is None:
                                    continue
                                child_type = child_desc.data(ROW_TYPE_ROLE)
                                child_item = item.child(r, col)
                                if child_type == STEP_TYPE:
                                    if child_item is not None:
                                        values.add(child_item.text())
                                elif child_type == GROUP_TYPE:
                                    if child_item is not None:
                                        values.add(child_item.text())
                                    collect_step_values(child_desc)
                        collect_step_values(group_item)
                        parent = group_item.parent() or self.model.invisibleRootItem()
                        row = group_item.row()
                        group_cell = parent.child(row, col)
                        if group_cell is None:
                            group_cell = PGCItem(item_type=field, item_data="")
                            parent.setChild(row, col, group_cell)
                        if len(values) == 1 and list(values)[0] != "":
                            group_cell.setText(next(iter(values)))
                            group_cell.setEditable(True)
                        else:
                            group_cell.setText("")
                            group_cell.setEditable(True)
                    
                    elif field == "Duration":
                        
                        def sum_child_durations(item):
                            total = 0.0
                            for r in range(item.rowCount()):
                                child_desc = item.child(r, 0)
                                child_type = child_desc.data(ROW_TYPE_ROLE)
                                if child_type == STEP_TYPE:
                                    rep_col = protocol_grid_fields.index("Repetitions")
                                    dur_col = protocol_grid_fields.index("Duration")
                                    repetitions = float(item.child(r, rep_col).text())
                                    duration = float(item.child(r, dur_col).text())
                                    total += repetitions * duration
                                elif child_type == GROUP_TYPE:
                                    update_group(child_desc)
                                    dur_col = protocol_grid_fields.index("Duration")
                                    subgroup_duration = float(item.child(r, dur_col).text())
                                    total += subgroup_duration
                            return total

                        rep_col = protocol_grid_fields.index("Repetitions")
                        try:
                            group_repetitions = float(group_item.child(group_item.row(), rep_col).text())
                        except Exception:
                            try:
                            #try to get from parent
                                group_repetitions = float(group_item.parent().child(group_item.row(), rep_col).text())
                            except Exception:    
                                group_repetitions = 1

                        parent = group_item.parent() or self.model.invisibleRootItem()
                        row = group_item.row()                        
                        group_repetitions = float(parent.child(row, rep_col).text())
                        total_duration = sum_child_durations(group_item) * group_repetitions   

                        parent = group_item.parent() or self.model.invisibleRootItem()
                        row = group_item.row()
                        dur_col = protocol_grid_fields.index("Duration")
                        group_duration_cell = parent.child(row, dur_col)
                        if group_duration_cell is None:
                            group_duration_cell = PGCItem(item_type="Duration", item_data="")
                            parent.setChild(row, dur_col, group_duration_cell)
                        group_duration_cell.setText(f"{total_duration:.2f}")
                        group_duration_cell.setEditable(False)
            # recursion for sub-groups 
            for r in range(group_item.rowCount()):
                child_desc = group_item.child(r, 0)
                if child_desc is not None and child_desc.data(ROW_TYPE_ROLE) == GROUP_TYPE:
                    update_group(child_desc)
        # start actual function from root item
        root = self.model.invisibleRootItem()
        for row in range(root.rowCount()):
            desc_item = root.child(row, 0)
            if desc_item is not None and desc_item.data(ROW_TYPE_ROLE) == GROUP_TYPE:
                update_group(desc_item)                        

    # ---------- UI Actions ----------
    def show_edit_context_menu(self, pos):
        self.action_show_edit_context_menu.perform(pos=pos)

    def show_column_toggle_dialog(self, pos):
        self.action_show_column_toggle_dialog.perform()

    # ---------- Column Management ----------
    def get_column_state(self):
        visibility = [not self.tree.isColumnHidden(i) for i in range(self.model.columnCount())]
        widths = [self.tree.columnWidth(i) for i in range(self.model.columnCount())]
        return visibility, widths

    def set_column_state(self, visibility, widths):
        for i, visible in enumerate(visibility):
            self.tree.setColumnHidden(i, not visible)
        for i, width in enumerate(widths):
            self.tree.setColumnWidth(i, width)

    # --------- Functions to Maintain Row Selection -----------
    def get_selected_paths(self):
        selection_model = self.tree.selectionModel()
        selected = selection_model.selectedRows(0)
        paths = []
        for idx in selected:
            path = []
            item = self.model.itemFromIndex(idx)
            while item is not None:
                parent = item.parent()
                row = item.row()
                path.insert(0, row)
                item = parent
            paths.append(path)
        return paths

    def get_item_by_path(self, path):
        """
        Given a path (list of row indices), return the QStandardItem at column 0.
        Returns None if not found.
        """
        item = self.model.invisibleRootItem()
        for row in path:
            if row < 0 or row >= item.rowCount():
                return None
            item = item.child(row, 0)
            if item is None:
                return None
        return item

    def restore_row_selection_by_paths(self, paths):
        selection_model = self.tree.selectionModel()
        selection_model.clearSelection()
        for path in paths:
            item = self.get_item_by_path(path)
            if item is not None:
                idx = item.index()
                selection_model.select(idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)

    def get_extreme_path(self, paths, extreme="min"):
        """
        Returns the smallest or largest path from a list of paths.
        """
        if not paths:
            return None
        return min(paths) if extreme == "min" else max(paths)
    
    def get_post_delete_selection_path(self, selected_paths):
        """
        Given a row(s) at its path(s) to be deleted, returns the path to select after deletion.
        - If the deleted rows are not at the end, select the row that takes their place (the row that was immediately after the last deleted row).
        - If the deleted rows are at the end, select the last remaining row (the row above the deleted group).
        """
        if not selected_paths:
            return None
        sorted_paths = sorted(selected_paths)
        first_path = sorted_paths[0]
        last_path = sorted_paths[-1]
        parent_path = last_path[:-1]
        parent = self.get_item_by_path(parent_path) or self.model.invisibleRootItem()
        row_after = last_path[-1] 
        if parent.rowCount() > row_after:
            return parent_path + [row_after]
        elif parent.rowCount() > 0:
            return parent_path + [parent.rowCount() - 1]
        else:
            return None
        
    def filter_top_level_row_refs(self, row_refs):
        """
        Given a list of (parent, row) tuples, return only those that are not children of any other selected row.
        """
        # Convert to paths for easy comparison
        def get_path(parent, row):
            path = []
            item = parent.child(row, 0)
            while item is not None:
                p = item.parent()
                r = item.row()
                path.insert(0, r)
                item = p
            return path

        paths = [get_path(parent, row) for parent, row in row_refs]
        top_level = []
        for i, path in enumerate(paths):
            if not any(path[:len(other)] == other for j, other in enumerate(paths) if j != i):
                top_level.append(row_refs[i])
        return top_level
    # ---------- ----------------------------------- ----------

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
        row_refs = self.filter_top_level_row_refs(row_refs)
        if not row_refs:
            self._copied_rows = None
            return
        self._copied_rows = []
        for parent, row in row_refs:
            # Only column 0 needs recursive clone, others are just data
            items = [parent.child(row, col).clone() for col in range(self.model.columnCount())]
            self._copied_rows.append(items)

    def cut_selected(self):
        self.state.snapshot_for_undo()
        self.copy_selected()
        self.delete_selected()

    def paste_selected(self, above=True):
        selected_paths = self.get_selected_paths()
        self.state.snapshot_for_undo()
        if not selected_paths:
            parent = self.model.invisibleRootItem()
            row = parent.rowCount()
            target_path = []
        else:
            if above:
                target_path = self.get_extreme_path(selected_paths, "min")
                parent_path = target_path[:-1]
                row = target_path[-1]
            else:
                target_path = self.get_extreme_path(selected_paths, "max")
                parent_path = target_path[:-1]
                row = target_path[-1] + 1
            parent = self.get_item_by_path(parent_path) or self.model.invisibleRootItem()
        if not self._copied_rows:
            return
        for r, items in enumerate(self._copied_rows):
            parent.insertRow(row + r, [item.clone() for item in items])
        self.save_to_state()
        reassign_ids(self.model)
        self.tree.expandAll()
        if target_path:
            self.restore_row_selection_by_paths([target_path])
        else:
            self.restore_row_selection_by_paths([])
        self.update_all_group_aggregations()
    
    def paste_into(self):
        """
        Paste copied/cut rows into selected group.
        If selected item is a step, then paste below it. 
        """
        selected_paths = self.get_selected_paths()
        self.state.snapshot_for_undo()
        if not selected_paths or not  self._copied_rows:
            return 
        target_path = selected_paths[0]
        target_item = self.get_item_by_path(target_path)
        if target_item and target_item.data(ROW_TYPE_ROLE) == GROUP_TYPE:
            parent = target_item
            row = parent.rowCount()
            for r, items in enumerate(self._copied_rows):
                parent.insertRow(row + r, [item.clone() for item in items])
            self.save_to_state()
            reassign_ids(self.model)
            self.tree.expandAll()
            if parent.rowCount() > 0:
                new_child_path = target_path + [row]
                self.restore_row_selection_by_paths([new_child_path])
            else:
                self.restore_row_selection_by_paths([])
        else:
            self.paste_selected(above=False)
        self.update_all_group_aggregations()

    def delete_selected(self):
        selected_paths = self.get_selected_paths()
        self.state.snapshot_for_undo()
        row_refs = self.get_selected_rows(for_deletion=True)
        row_refs = self.filter_top_level_row_refs(row_refs)
        for parent, row in row_refs:
            parent.removeRow(row)
        self.save_to_state()
        reassign_ids(self.model)
        post_delete_path = self.get_post_delete_selection_path(selected_paths)
        if post_delete_path:
            self.restore_row_selection_by_paths([post_delete_path])
        else:
            self.restore_row_selection_by_paths([])
        if self.model.invisibleRootItem().rowCount() == 0:
            self.add_step(into=False)
        self.update_all_group_aggregations()

    def insert_step(self):
        selected_paths = self.get_selected_paths()
        self.state.snapshot_for_undo()
        top_path = self.get_extreme_path(selected_paths, "min")
        if top_path is None:
            parent = self.model.invisibleRootItem()
            row = parent.rowCount()
        else:
            parent_path = top_path[:-1]
            row = top_path[-1]
            parent = self.get_item_by_path(parent_path) or self.model.invisibleRootItem()
        step_items = make_row(step_defaults, overrides={"Description": f"Step", "ID": ""}, row_type=STEP_TYPE)
        parent.insertRow(row, step_items)
        self.save_to_state()
        reassign_ids(self.model)
        self.tree.expandAll()
        # after insert, the original top_path is now at last index + 1
        if top_path:
            new_path = top_path.copy()
            new_path[-1] += 1
            self.restore_row_selection_by_paths([new_path])
        else:
            self.restore_row_selection_by_paths([])
        self.update_all_group_aggregations()

    def insert_group(self):
        selected_paths = self.get_selected_paths()
        self.state.snapshot_for_undo()
        top_path = self.get_extreme_path(selected_paths, "min")
        if top_path is None:
            parent = self.model.invisibleRootItem()
            row = parent.rowCount()
        else:
            parent_path = top_path[:-1]
            row = top_path[-1]
            parent = self.get_item_by_path(parent_path) or self.model.invisibleRootItem()
        group_items = make_row(group_defaults, overrides={"Description": "Group"}, row_type=GROUP_TYPE)
        parent.insertRow(row, group_items)
        self.save_to_state()
        reassign_ids(self.model)
        self.tree.expandAll()
        # after insert, the original top_path is now at last index + 1
        if top_path:
            new_path = top_path.copy()
            new_path[-1] += 1
            self.restore_row_selection_by_paths([new_path])
        else:
            self.restore_row_selection_by_paths([])
        self.update_all_group_aggregations()

    def add_group(self, into=False):
        """
        Add a group to the tree view. If into is True, the group is added as a child of the selected item.
        Otherwise, the group is added as a sibling of the selected item.

        Removes necessity to deselect a direct child of root and setting focus on root to add a group as a
        sibling in the uppermost level.
        """
        selected_paths = self.get_selected_paths()
        self.state.snapshot_for_undo()
        # Find the bottommost selected row
        bottom_path = self.get_extreme_path(selected_paths, "max")
        parent = self.model.invisibleRootItem()
        if bottom_path is not None:
            selected_item = self.get_item_by_path(bottom_path)
            if into and selected_item and selected_item.data(ROW_TYPE_ROLE) == GROUP_TYPE:
                parent = selected_item
            else:
                parent_path = bottom_path[:-1]
                parent = self.get_item_by_path(parent_path) or self.model.invisibleRootItem()
        group_items = make_row(group_defaults, overrides={"Description": "Group"}, row_type=GROUP_TYPE)
        parent.appendRow(group_items)
        self.save_to_state()
        reassign_ids(self.model)
        self.tree.expandAll()
        self.restore_row_selection_by_paths(selected_paths)
        self.update_all_group_aggregations()

    def add_step(self, into=False):
        selected_paths = self.get_selected_paths()
        self.state.snapshot_for_undo()
        bottom_path = self.get_extreme_path(selected_paths, "max")
        parent = self.model.invisibleRootItem()
        if bottom_path is not None:
            selected_item = self.get_item_by_path(bottom_path)
            if into and selected_item and selected_item.data(ROW_TYPE_ROLE) == GROUP_TYPE:
                parent = selected_item
            else:
                parent_path = bottom_path[:-1]
                parent = self.get_item_by_path(parent_path) or self.model.invisibleRootItem()
        step_items = make_row(step_defaults, overrides={"Description": f"Step", "ID": ""}, row_type=STEP_TYPE)
        parent.appendRow(step_items)
        self.save_to_state()
        reassign_ids(self.model)
        self.tree.expandAll()
        self.restore_row_selection_by_paths(selected_paths)
        self.update_all_group_aggregations()

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
            self.state.undo_stack.clear()
            self.state.redo_stack.clear()

from PySide6.QtWidgets import QApplication, QMainWindow
import sys

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Protocol Editor Demo")
        self.setCentralWidget(PGCWidget())
        self.resize(1300, 500)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
