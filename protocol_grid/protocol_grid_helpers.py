from PySide6.QtCore import Qt, QItemSelectionModel, QTimer
from PySide6.QtWidgets import QStyledItemDelegate, QLineEdit, QCheckBox, QSpinBox, QDoubleSpinBox
from PySide6.QtGui import QStandardItem
from protocol_grid.consts import GROUP_TYPE, STEP_TYPE, ROW_TYPE_ROLE, protocol_grid_fields


class PGCItem(QStandardItem):
    def __init__(self, text=""):
        super().__init__(text)
        
    def setEditable(self, editable):
        flags = self.flags()
        if editable:
            flags |= Qt.ItemIsEditable
        else:
            flags &= ~Qt.ItemIsEditable
        self.setFlags(flags)


class ProtocolGridDelegate(QStyledItemDelegate):
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
    def createEditor(self, parent, option, index):
        field = protocol_grid_fields[index.column()]
        
        if field in ("Video", "Magnet"):
            editor = QCheckBox(parent)
            return editor
        elif field in ("Magnet Height"):
            editor = QSpinBox(parent)
            editor.setMinimum(0)
            editor.setMaximum(10)
            return editor
        elif field in ("Repetitions", "Trail Length"):
            editor = QSpinBox(parent)
            editor.setMinimum(1)
            editor.setMaximum(10000)
            return editor
        elif field in ("Frequency"):
            editor = QSpinBox(parent)
            editor.setMinimum(100)
            editor.setMaximum(20000)
            editor.setSingleStep(100)
            return editor
        elif field in ("Trail Overlay", "Max. Path Length"):
            editor = QSpinBox(parent)
            editor.setMinimum(0)
            editor.setMaximum(1000)
            return editor
        elif field in ("Duration"):
            editor = QDoubleSpinBox(parent)
            editor.setMinimum(0.0)
            editor.setMaximum(10000.0)
            editor.setDecimals(1)
            editor.setSingleStep(0.1)
            return editor
        elif field in ("Voltage"):
            editor = QDoubleSpinBox(parent)
            editor.setMinimum(30.0)
            editor.setMaximum(150.0)
            editor.setDecimals(1)
            editor.setSingleStep(0.5)
            return editor        
        elif field in ("Volume Threshold"):
            editor = QDoubleSpinBox(parent)
            editor.setMinimum(0.00)
            editor.setMaximum(1.00)
            editor.setDecimals(2)
            editor.setSingleStep(0.01)
            return editor
        elif field in ("Repeat Duration", "Run Time"):
            editor = QDoubleSpinBox(parent)
            editor.setMinimum(0.0)
            editor.setMaximum(99999.9)
            editor.setDecimals(1)
            return editor
        else:
            return QLineEdit(parent)
            
    def setEditorData(self, editor, index):
        field = protocol_grid_fields[index.column()]
        
        if field in ("Video"):
            checked = index.model().data(index, Qt.CheckStateRole) == Qt.Checked
            editor.setChecked(checked)
        elif field in ("Magnet"):
            checked = index.model().data(index, Qt.CheckStateRole) == 2
            editor.setChecked(checked)
        elif isinstance(editor, (QSpinBox, QDoubleSpinBox)):
            try:
                value = float(index.model().data(index, Qt.DisplayRole) or 0)
                editor.setValue(value)
            except (ValueError, TypeError):
                editor.setValue(0)
        else:
            text = index.model().data(index, Qt.DisplayRole) or ""
            editor.setText(str(text))
            
    def setModelData(self, editor, model, index):
        field = protocol_grid_fields[index.column()]
        if isinstance(editor, QCheckBox) and field != "Magnet":
            checked = editor.isChecked()
            model.setData(index, Qt.Checked if checked else Qt.Unchecked, Qt.CheckStateRole)
            item = model.itemFromIndex(index)
            if item is not None:
                item.emitDataChanged()
        elif isinstance(editor, (QSpinBox, QDoubleSpinBox)) and field != "Magnet Height":
            value = editor.value()
            if isinstance(editor, QDoubleSpinBox):
                model.setData(index, f"{value:.1f}", Qt.EditRole)
            else:
                model.setData(index, str(int(value)), Qt.EditRole)
        elif field == "Magnet Height":
            value = editor.value() if hasattr(editor, "value") else editor.text()
            model.setData(index, str(value), Qt.EditRole)
            model.setData(index, str(value), Qt.UserRole + 2)
        else:
            text = editor.text()
            model.setData(index, text, Qt.EditRole)

        widget = self.parent()
        if hasattr(widget, "sync_to_state"):
            widget.sync_to_state()


def make_row(defaults, overrides=None, row_type=STEP_TYPE, children=None):
    overrides = overrides or {}
    items = []
    magnet_checked = False

    for field in protocol_grid_fields:
        value = overrides.get(field, defaults.get(field, ""))
        item = PGCItem(str(value))

        if field == "Description":
            item.setData(row_type, ROW_TYPE_ROLE)

        if row_type == STEP_TYPE and field in ("Video", "Magnet"):
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            checked = str(value).strip().lower() in ("1", "true", "yes", "on")
            item.setData(Qt.Checked if checked else Qt.Unchecked, Qt.CheckStateRole)
            item.setText("")
            if field == "Magnet":
                magnet_checked = checked
        elif row_type == STEP_TYPE and field == "Magnet Height":
            item.setData(str(value), Qt.UserRole + 2)
            if not magnet_checked:
                item.setEditable(False)
                item.setText("")
            else:
                item.setEditable(True)
                last_value = item.data(Qt.UserRole + 2)
                if last_value is not None and last_value != "":
                    item.setText(str(last_value))
        elif row_type == STEP_TYPE and field in ("Max. Path Length", "Run Time"):
            item.setEditable(False)
        elif row_type == GROUP_TYPE:
            if field in ("Description", "Voltage", "Frequency", "Trail Length"):
                item.setEditable(True)
            elif field in ("Duration", "Run Time", "Repetitions", "ID"):
                item.setEditable(False)
            else:
                item.setEditable(False)
                item.setText("")

        items.append(item)

    if row_type == GROUP_TYPE and children:
        calculate_group_aggregation_from_children(items, children)

    return items


def calculate_group_aggregation(group_item):
    if not group_item or not group_item.hasChildren():
        return
        
    parent = group_item.parent() or group_item.model().invisibleRootItem()
    row = group_item.row()
    
    total_repetitions = 0
    total_duration = 0.0
    total_run_time = 0.0
    
    def collect_from_children(parent_item):
        nonlocal total_repetitions, total_duration, total_run_time
        
        for child_row in range(parent_item.rowCount()):
            child_desc = parent_item.child(child_row, 0)
            if not child_desc:
                continue
                
            child_type = child_desc.data(ROW_TYPE_ROLE)
            
            if child_type == STEP_TYPE:
                try:
                    rep_item = parent_item.child(child_row, protocol_grid_fields.index("Repetitions"))
                    dur_item = parent_item.child(child_row, protocol_grid_fields.index("Duration"))
                    run_item = parent_item.child(child_row, protocol_grid_fields.index("Run Time"))
                    
                    if rep_item and dur_item and run_item:
                        reps = int(rep_item.text() or "1")
                        dur = float(dur_item.text() or "1.0")
                        run = float(run_item.text() or "0.0")
                        
                        total_repetitions += reps
                        total_duration += dur
                        total_run_time += run
                except (ValueError, IndexError):
                    pass
            elif child_type == GROUP_TYPE and child_desc.hasChildren():
                collect_from_children(child_desc)
                
    collect_from_children(group_item)
    
    try:
        rep_item = parent.child(row, protocol_grid_fields.index("Repetitions"))
        dur_item = parent.child(row, protocol_grid_fields.index("Duration"))
        run_item = parent.child(row, protocol_grid_fields.index("Run Time"))
        
        if rep_item:
            rep_item.setText(str(total_repetitions))
        if dur_item:
            dur_item.setText(f"{total_duration:.1f}")
        if run_item:
            run_item.setText(f"{total_run_time:.2f}")
    except IndexError:
        pass


def calculate_group_aggregation_from_children(group_items, children):
    agg_fields = ["Voltage", "Frequency", "Trail Length"]
    agg_values = {field: None for field in agg_fields}
    agg_consistent = {field: True for field in agg_fields}
    agg_found = {field: False for field in agg_fields}

    total_duration = 0.0
    total_run_time = 0.0

    def collect_from_items(child_rows):
        nonlocal agg_values, agg_consistent, agg_found, total_duration, total_run_time

        for child_row in child_rows:
            if not child_row or not isinstance(child_row, list):
                continue

            try:
                desc_item = child_row[0]
                child_type = desc_item.data(ROW_TYPE_ROLE)

                if child_type == STEP_TYPE:
                    for field in agg_fields:
                        idx = protocol_grid_fields.index(field)
                        val = child_row[idx].text()
                        if not agg_found[field]:
                            agg_values[field] = val
                            agg_found[field] = True
                        elif agg_values[field] != val:
                            agg_consistent[field] = False

                    dur_idx = protocol_grid_fields.index("Duration")
                    rep_idx = protocol_grid_fields.index("Repetitions")
                    run_idx = protocol_grid_fields.index("Run Time")
                    try:
                        duration = float(child_row[dur_idx].text() or "0")
                        repetitions = int(child_row[rep_idx].text() or "1")
                        run_time = float(child_row[run_idx].text() or "0")
                    except ValueError:
                        duration = 0.0
                        repetitions = 1
                        run_time = 0.0
                    total_duration += duration * repetitions
                    total_run_time += run_time

                elif child_type == GROUP_TYPE:
                    dur_idx = protocol_grid_fields.index("Duration")
                    run_idx = protocol_grid_fields.index("Run Time")
                    try:
                        duration = float(child_row[dur_idx].text() or "0")
                        run_time = float(child_row[run_idx].text() or "0")
                    except ValueError:
                        duration = 0.0
                        run_time = 0.0
                    total_duration += duration
                    total_run_time += run_time

                    sub_rows = [
                        [desc_item.child(r, c) for c in range(desc_item.columnCount())]
                        for r in range(desc_item.rowCount())
                    ]
                    collect_from_items(sub_rows)
            except (ValueError, IndexError, AttributeError):
                pass

    collect_from_items(children)

    try:
        for field in agg_fields:
            idx = protocol_grid_fields.index(field)
            item = group_items[idx]
            if agg_found[field] and agg_consistent[field]:
                item.setText(agg_values[field])
            else:
                item.setText("")

        dur_idx = protocol_grid_fields.index("Duration")
        run_idx = protocol_grid_fields.index("Run Time")
        group_items[dur_idx].setText(f"{total_duration:.1f}")
        group_items[run_idx].setText(f"{total_run_time:.2f}")
    except IndexError:
        pass


def clamp_trail_overlay(parent):
    if hasattr(parent, "rowCount") and hasattr(parent, "columnCount"):
        row_count = parent.rowCount()
        item_getter = (lambda r, c: parent.item(r, c)) if hasattr(parent, "item") else (lambda r, c: parent.child(r, c))
    else:
        return
        
    for row in range(row_count):
        desc_item = item_getter(row, 0)
        if desc_item is None:
            continue
            
        if desc_item.hasChildren():
            clamp_trail_overlay(desc_item)
        else:
            try:
                trail_length_col = protocol_grid_fields.index("Trail Length")
                overlay_col = protocol_grid_fields.index("Trail Overlay")
                trail_length_item = item_getter(row, trail_length_col)
                overlay_item = item_getter(row, overlay_col)
                
                trail_length = int(trail_length_item.text())
                max_overlay = max(0, trail_length - 1)
                overlay_val = int(overlay_item.text())
                
                if overlay_val > max_overlay:
                    overlay_item.setText(str(max_overlay))
            except Exception:
                pass