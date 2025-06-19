from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import (QStyledItemDelegate, QSpinBox, QDoubleSpinBox,
                               QLineEdit, QCheckBox)

from protocol_grid.consts import (protocol_grid_fields, ROW_TYPE_ROLE,
                                  GROUP_TYPE, STEP_TYPE, step_defaults)


class ProtocolGridDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        col = index.column()
        field = protocol_grid_fields[col]
        if field in ("Label", "Message"):            
            return QLineEdit(parent)
        elif field in ("Repetitions", "Repeat Duration", "Trail Length"):
            editor = QSpinBox(parent)
            editor.setMinimum(1)
            editor.setMaximum(10000)
            return editor
        elif field == "Video":
            cb = QCheckBox(parent)
            cb.setText("")
            cb.setTristate(False)
            return cb
        elif field in ("Duration", "Voltage", "Frequency", "Volume Threshold"):
            editor = QDoubleSpinBox(parent)
            editor.setMinimum(0.0)
            editor.setMaximum(10000.0)
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
            editor.setChecked(bool(int(value)) if value not in (None, "") else False)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        col = index.column()
        field = protocol_grid_fields[col]
        if isinstance(editor, QLineEdit):
            model.setData(index, editor.text(), Qt.ItemDataRole.EditRole)
        elif isinstance(editor, QSpinBox):
            model.setData(index, editor.value(), Qt.ItemDataRole.EditRole)
        elif isinstance(editor, QDoubleSpinBox):
            model.setData(index, editor.value(), Qt.ItemDataRole.EditRole)
        elif isinstance(editor, QCheckBox):
            checked = int(editor.isChecked())
            model.setData(index, checked, Qt.ItemDataRole.EditRole)
            model.setData(index, Qt.Checked if checked else Qt.Unchecked, Qt.CheckStateRole)
            model.setData(index, "", Qt.DisplayRole)
        else:
            super().setModelData(editor, model, index)


class PGCItem(QStandardItem):
    def __init__(self, item_type=None, item_data=None):
        if item_type == "Video":
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
        # only clone children for root (-1) and column 0
        if self.column() in (-1, 0):
            for row in range(self.rowCount()):
                if self.child(row, 0) is not None:
                    child_row = [self.child(row, col).clone() if self.child(row, col) is not None else None for col in range(self.columnCount())]
                    new_item.appendRow(child_row)
        return new_item
    

def make_row(defaults, overrides=None, row_type=None):
    """
    Create row (Step/Group) using default values defined in consts.py
    """
    overrides = overrides or {}
    items = []
    for i, field in enumerate(protocol_grid_fields):
        value = overrides.get(field, defaults.get(field, ""))
        display_value = "" if field == "Video" else value
        item = PGCItem(item_type=field, item_data=display_value)
        if field == "Description" and row_type:
            item.setData(row_type, ROW_TYPE_ROLE)
        if field == "ID":
            item.setEditable(False)
        else:
            item.setEditable(True)
        if field == "Video":
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable) # prevent editing anywhere else
                                                             # on the cell around the actual checkbox
            checked = (
                value == 1 or
                value == "1" or
                str(value).lower() in ("true")
            )
            item.setData(Qt.Checked if checked else Qt.Unchecked, Qt.CheckStateRole)
        items.append(item)
    return items

def int_to_letters(n):
    result=''
    while n > 0:
        n -= 1
        result = chr(65 + (n % 26)) + result
        n //= 26
    return result

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

def snapshot_for_undo(model, undo_stack, redo_stack, max_undo=6):
    """
    Save a deep copy of the current model to the undo stack.
    """
    root_item = model.invisibleRootItem()
    clone = [
        [root_item.child(row, col).clone() for col in range(model.columnCount())]
        for row in range(root_item.rowCount())
    ]
    undo_stack.append(clone)
    if len(undo_stack) > max_undo:
        undo_stack[:] = undo_stack[-max_undo:]
    redo_stack.clear()

def undo_last(model, undo_stack, redo_stack, reassign_step_ids_callback):
    if not undo_stack:
        return
    current_state = [
        [model.invisibleRootItem().child(row, col).clone()
         for col in range(model.columnCount())]
        for row in range(model.invisibleRootItem().rowCount())
    ]
    redo_stack.append(current_state)
    last_state = undo_stack.pop()
    clear_view(model)
    for row_items in last_state:
        model.invisibleRootItem().appendRow([item.clone() for item in row_items])
    reassign_step_ids_callback()
    # If you want: tree.expandAll()  # pass the tree if you want to do this

def redo_last(model, undo_stack, redo_stack, reassign_step_ids_callback):
    if not redo_stack:
        return
    current_state = [
        [model.invisibleRootItem().child(row, col).clone()
         for col in range(model.columnCount())]
        for row in range(model.invisibleRootItem().rowCount())
    ]
    undo_stack.append(current_state)
    next_state = redo_stack.pop()
    clear_view(model)
    for row_items in next_state:
        model.invisibleRootItem().appendRow([item.clone() for item in row_items])
    reassign_step_ids_callback()

def clear_view(model):
    model.clear()
    model.setHorizontalHeaderLabels(protocol_grid_fields)

def reassign_step_ids(model):
    step_id = 1
    group_id = 1
    def assign(parent):
        nonlocal step_id, group_id
        for row in range(parent.rowCount()):
            desc_item = parent.child(row, 0)
            id_item = parent.child(row, 1)
            row_type = desc_item.data(ROW_TYPE_ROLE)
            if row_type == STEP_TYPE:
                id_item.setText(str(step_id))
                step_id += 1
            elif row_type == GROUP_TYPE:
                id_item.setText(int_to_letters(group_id))
                group_id += 1
            if desc_item.hasChildren():
                assign(desc_item)
    assign(model.invisibleRootItem())

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
                        value = item.text() if field != "Video" else (
                            1 if item.data(Qt.CheckStateRole) == Qt.Checked else 0
                        )
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

    root_item = model.invisibleRootItem()
    return parse_seq(root_item)

def populate_treeview(model, protocol_sequence, make_row_func, step_defaults, group_defaults):
    clear_view(model)
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
                group_items = make_row_func(
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
                step_items = make_row_func(
                    step_defaults,
                    overrides=step_data,
                    row_type=STEP_TYPE
                )
                parent.appendRow(step_items)
    root_item = model.invisibleRootItem()
    add_seq(root_item, protocol_sequence)