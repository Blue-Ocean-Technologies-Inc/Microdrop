from PySide6.QtCore import Qt, QItemSelectionModel, QTimer
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import (QStyledItemDelegate, QSpinBox, QDoubleSpinBox,
                               QLineEdit, QCheckBox)

from protocol_grid.consts import (protocol_grid_fields, ROW_TYPE_ROLE,
                                  GROUP_TYPE, STEP_TYPE, step_defaults)


class ProtocolGridDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        col = index.column()
        field = protocol_grid_fields[col]
        model = index.model()
        row = index.row()
        if field == "Trail Overlay":
            trail_length_col = protocol_grid_fields.index("Trail Length")
            item_parent = index.model().itemFromIndex(index.parent()) if index.parent().isValid() else None
            if item_parent:
                trail_length_item = item_parent.child(index.row(), trail_length_col)
            else:
                trail_length_item = model.item(index.row(), trail_length_col)
            max_val = 0
            try:
                max_val = max(0, int(trail_length_item.text()) - 1)
            except Exception:
                max_val = 0
            editor = QSpinBox(parent)
            editor.setMinimum(0)
            editor.setMaximum(max_val)
            return editor
        if field == "Magnet Height":
            parent_item = model.itemFromIndex(index.parent()) if index.parent().isValid() else model.invisibleRootItem()
            magnet_col = protocol_grid_fields.index("Magnet")
            magnet_item = parent_item.child(index.row(), magnet_col)
            if magnet_item and magnet_item.data(Qt.CheckStateRole):
                editor = QSpinBox(parent)
                editor.setMinimum(0)
                editor.setMaximum(10)
                return editor
            else:
                return None
        if field in ("Label", "Message"):
            return QLineEdit(parent)
        elif field in ("Repetitions", "Repeat Duration", "Trail Length"):
            editor = QSpinBox(parent)
            editor.setMinimum(1)
            editor.setMaximum(10000)
            return editor
        elif field in ("Magnet", "Video"):
            cb = QCheckBox(parent)
            cb.setText("")
            cb.setTristate(False)
            return cb
        elif field in ("Duration", "Voltage", "Frequency"):
            editor = QDoubleSpinBox(parent)
            editor.setMinimum(0.0)
            editor.setMaximum(10000.0)
            editor.setDecimals(2)
            return editor
        elif field in ("Volume Threshold"):
            editor = QDoubleSpinBox(parent)
            editor.setMinimum(0.0)
            editor.setMaximum(1.00)
            editor.setDecimals(2)
            return editor
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.ItemDataRole.EditRole)
        col = index.column()
        field = protocol_grid_fields[col]
        if isinstance(editor, QLineEdit):
            editor.setText(str(value) if value is not None else "")
        elif isinstance(editor, QSpinBox):
            editor.setValue(int(value) if value else 0)
        elif isinstance(editor, QDoubleSpinBox):
            editor.setValue(float(value) if value else 0.0)
        elif isinstance(editor, QCheckBox):
            checked = index.model().data(index, Qt.CheckStateRole) == Qt.Checked
            editor.setChecked(checked)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        col = index.column()
        field = protocol_grid_fields[col]
        row = index.row()
        if isinstance(editor, QLineEdit):
            model.setData(index, editor.text(), Qt.ItemDataRole.EditRole)
        elif isinstance(editor, QSpinBox):
            value = editor.value()
            current_value = index.model().data(index, Qt.ItemDataRole.EditRole)
            if value != current_value:
                model.setData(index, value, Qt.ItemDataRole.EditRole)
                if field == "Trail Length":
                    overlay_col = protocol_grid_fields.index("Trail Overlay")
                    overlay_idx = model.index(row, overlay_col)
                    overlay_item = model.itemFromIndex(overlay_idx)
                    try:
                        max_overlay = max(0, int(value) - 1)
                    except Exception:
                        max_overlay = 0
                    try:
                        overlay_val = int(overlay_item.text())
                    except Exception:
                        overlay_val = 0
                    if overlay_val > max_overlay:
                        overlay_item.setText(str(max_overlay))
                    if overlay_val < 0:
                        overlay_item.setText("0")
                    view = self.parent().tree if hasattr(self.parent(), "tree") else None
                    if view:
                        view.closePersistentEditor(overlay_idx)
        elif isinstance(editor, QDoubleSpinBox):
            model.setData(index, editor.value(), Qt.ItemDataRole.EditRole)
        elif isinstance(editor, QCheckBox):
            checked = int(editor.isChecked())
            model.setData(index, checked, Qt.ItemDataRole.EditRole)
            model.setData(index, Qt.Checked if checked else Qt.Unchecked, Qt.CheckStateRole)
            model.setData(index, "", Qt.DisplayRole)
            widget = self.parent()
            if hasattr(widget, "save_to_state"):
                widget.save_to_state()
        else:
            super().setModelData(editor, model, index)


class PGCItem(QStandardItem):
    def __init__(self, item_type=None, item_data=None):
        if item_type in ("Video", "Magnet"):
            item_data = ""
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
        for role in range(Qt.UserRole + 100):
            value = self.data(role)
            if value is not None:
                new_item.setData(value, role)
        check_state = self.data(Qt.CheckStateRole)
        new_item.setData(check_state, Qt.CheckStateRole)
        # only clone children for root (-1) and column 0
        if self.column() in (-1, 0):
            for row in range(self.rowCount()):
                if self.child(row, 0) is not None:
                    child_row = [self.child(row, col).clone() if self.child(row, col) is not None else None for col in range(self.columnCount())]
                    new_item.appendRow(child_row)
        return new_item
    

def make_row(defaults, overrides=None, row_type=None, children=None):
    overrides = overrides or {}
    items = []
    magnet_checked = False

    # For group rows, check children for aggregation
    group_agg_fields = ("Voltage", "Frequency", "Trail Length")
    group_agg_values = {}
    if row_type == GROUP_TYPE and children:
        for field in group_agg_fields:
            values = set()
            for child in children:
                idx = protocol_grid_fields.index(field)
                val = child[idx].text()
                values.add(val)
            if len(values) == 1:
                group_agg_values[field] = values.pop()
            else:
                group_agg_values[field] = None

    for i, field in enumerate(protocol_grid_fields):
        value = overrides.get(field, defaults.get(field, ""))
        display_value = "" if field in ("Video", "Magnet") else value
        item = PGCItem(item_type=field, item_data=display_value)
        if field == "Description" and row_type:
            item.setData(row_type, ROW_TYPE_ROLE)
        if field == "ID":
            item.setEditable(False)
        elif row_type == GROUP_TYPE and field in group_agg_fields:
            agg_val = group_agg_values.get(field)
            if agg_val is not None:
                item.setText(agg_val)
                item.setEditable(True)
            else:
                item.setText("")
                item.setEditable(False)
        elif row_type == GROUP_TYPE and field not in ("Description", "ID", "Repetitions", "Duration") and field not in group_agg_fields:
            item.setText("")
            item.setEditable(False)
        else:
            item.setEditable(True)
        if field in ("Video", "Magnet"):
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            checked = str(value).strip().lower() in ("1", "true", "yes", "on")
            item.setData(Qt.Checked if checked else Qt.Unchecked, Qt.CheckStateRole)
            if field == "Magnet":
                magnet_checked = checked
        if field == "Magnet Height":
            if not magnet_checked:
                item.setEditable(False)
                item.setData("", Qt.DisplayRole)
            else:
                item.setEditable(True)
                item.setData(value, Qt.DisplayRole)
        items.append(item)
    return items

def get_selected_rows(tree, model, for_deletion=False):
    """
    Returns list of (parent, row) for each unique row with at least one selected cell.
    - if for_deletion: sort by depth and descending row, for safe deletion.
    - else: preserve selection order (as returned by selectedRows(0)).
    """
    selection_model = tree.selectionModel()
    selected = selection_model.selectedRows(0)
    seen = set()
    row_refs = []
    for idx in selected:
        item = model.itemFromIndex(idx)
        parent = item.parent() or model.invisibleRootItem()
        row = item.row()
        key = (id(parent), row)
        if key not in seen:
            seen.add(key)
            row_refs.append((parent, row))
    if for_deletion:
        def get_depth(item):
            depth = 0  # depth needed for correct deletion order
            p = item.parent() or model.invisibleRootItem()
            while p != model.invisibleRootItem():
                depth += 1
                p = p.parent() or model.invisibleRootItem()
            return depth
        row_refs_with_depth = [((parent, row), get_depth(parent.child(row, 0))) for parent, row in row_refs]
        row_refs_with_depth.sort(key=lambda prd: (-prd[1], -prd[0][1]))  # deepest, then largest row index first
        return [pr for pr, _ in row_refs_with_depth]
    return row_refs

def invert_row_selection(tree, model):
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
    selection_model = tree.selectionModel()

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
    # step 3
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

def to_protocol_model(model):
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
                        value = (
                            1 if item.data(Qt.CheckStateRole) == Qt.Checked else 0
                        ) if field in ("Video", "Magnet") else item.text()
                        fields[field] = value
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
                        if field in ("Video", "Magnet"):
                            value = 1 if item.data(Qt.CheckStateRole) == Qt.Checked else 0
                        else:
                            value = item.text()
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

    root_item = model.invisibleRootItem()
    return parse_seq(root_item)

