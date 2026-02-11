from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QStyledItemDelegate,
    QLineEdit,
    QCheckBox,
    QSpinBox,
    QDoubleSpinBox,
    QAbstractItemView,
    QStyleOptionViewItem,
    QStyle,
    QApplication,
)
from PySide6.QtGui import QStandardItem

from dropbot_controller.consts import SET_VOLTAGE, SET_FREQUENCY
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from peripheral_controller.consts import MIN_ZSTAGE_HEIGHT_MM, MAX_ZSTAGE_HEIGHT_MM
from protocol_grid.consts import (
    GROUP_TYPE,
    STEP_TYPE,
    ROW_TYPE_ROLE,
    protocol_grid_fields,
    CHECKBOX_COLS,
    ALLOWED_group_fields,
)


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
        self.parent_widget = parent

    def paint(self, painter, option, index):
        """
        Overridden to prevent "Ghost Text" behind the editor.
        """
        # Do not paint any reading text in a cell where editing is in progress. Hand off to editor widget.
        _widget = option.widget
        if not (_widget.state() == QAbstractItemView.EditingState and _widget.currentIndex() == index):
            super().paint(painter, option, index)

    def createEditor(self, parent, option, index):
        # prevent editing during protocol execution
        if hasattr(self.parent_widget, 'is_protocol_running') and self.parent_widget.is_protocol_running():
            # during protocol execution, only allow editing in advanced mode for specific fields
            if hasattr(self.parent_widget, 'navigation_bar') and self.parent_widget.navigation_bar.is_advanced_user_mode():
                field = protocol_grid_fields[index.column()]
                if field in ("Voltage", "Frequency"):
                    pass
                else:
                    return None
            else:
                return None

        field = protocol_grid_fields[index.column()]

        if field == "Force":
            return None            
        if field in CHECKBOX_COLS:
            editor = QCheckBox(parent)
            return editor
        elif field in ("Magnet Height (mm)"):
            editor = QDoubleSpinBox(parent)
            editor.setFrame(False)  # Often looks better in tables

            # 1. Define the "Magic Number" for Default
            # We go slightly below the actual minimum to store the "Default" state
            self.special_value = MIN_ZSTAGE_HEIGHT_MM - 0.5

            # 2. Set Range including the special value
            editor.setRange(self.special_value, MAX_ZSTAGE_HEIGHT_MM)

            # 3. Map the minimum value to the text "Default"
            editor.setSpecialValueText("Default")

            editor.setDecimals(2)
            editor.setSingleStep(0.1)
            return editor
        elif field in ("Repetitions", "Trail Length"):
            editor = QSpinBox(parent)
            editor.setMinimum(1)
            editor.setMaximum(10000)
            return editor
        elif field == "Frequency":
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
        elif field == "Duration":
            editor = QDoubleSpinBox(parent)
            editor.setMinimum(0.0)
            editor.setMaximum(10000.0)
            editor.setDecimals(1)
            editor.setSingleStep(0.1)
            return editor
        elif field == "Voltage":
            editor = QDoubleSpinBox(parent)
            editor.setMinimum(30.0)
            editor.setMaximum(150.0)
            editor.setDecimals(1)
            editor.setSingleStep(0.5)
            return editor        
        elif field == "Volume Threshold":
            editor = QDoubleSpinBox(parent)
            editor.setMinimum(0.00)
            editor.setMaximum(1.00)
            editor.setDecimals(2)
            editor.setSingleStep(0.05)
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

        if field == "Force":
            return

            # --- 1. Checkboxes ---
        if field in CHECKBOX_COLS:
            check_state = index.model().data(index, Qt.CheckStateRole)
            if check_state is not None:
                checked = check_state == Qt.Checked or check_state == 2
            else:
                text_value = index.model().data(index, Qt.DisplayRole) or ""
                checked = str(text_value).strip().lower() in ("1", "true", "yes", "on")
            editor.setChecked(checked)
            return

        # --- 2. Magnet Height (Special Handling for "Default") ---
        if field == "Magnet Height (mm)" and isinstance(editor, QDoubleSpinBox):
            raw_data = index.model().data(index, Qt.EditRole)

            # If data is "Default", set editor to its minimum (Magic Number)
            if raw_data == "Default":
                editor.setValue(editor.minimum())
            else:
                try:
                    editor.setValue(float(raw_data))
                except (ValueError, TypeError):
                    editor.setValue(editor.minimum())
            return

        # --- 3. Standard SpinBoxes ---
        if isinstance(editor, (QSpinBox, QDoubleSpinBox)):
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

        # --- 1. Guard Clauses (Execution Mode) ---
        if hasattr(self.parent_widget, 'is_protocol_running') and self.parent_widget.is_protocol_running():
            is_advanced = hasattr(self.parent_widget, 'navigation_bar') and \
                          self.parent_widget.navigation_bar.is_advanced_user_mode()

            if not is_advanced or field not in ("Voltage", "Frequency"):
                return

        if field == "Force":
            return

        # --- 2. Checkboxes ---
        if isinstance(editor, QCheckBox):
            checked = editor.isChecked()
            model.setData(index, Qt.Checked if checked else Qt.Unchecked, Qt.CheckStateRole)
            model.setData(index, "", Qt.DisplayRole)  # Clear text so only checkbox shows

            item = model.itemFromIndex(index)
            if item: item.emitDataChanged()

        # --- 3. SpinBoxes (Logic separated from Side Effects) ---
        elif isinstance(editor, (QSpinBox, QDoubleSpinBox)):
            value = editor.value()

            # A. Side Effects (Publishing)
            if field == "Voltage":
                publish_message(str(value), SET_VOLTAGE)
            elif field == "Frequency":
                publish_message(str(value), SET_FREQUENCY)

            # B. Saving Data
            if field == "Magnet Height (mm)":
                # Check if we are at the "Magic Number" for Default
                if value == editor.minimum():
                    model.setData(index, "Default", Qt.EditRole)
                    model.setData(index, "Default", Qt.UserRole + 2)
                else:
                    # Save as standard string/float
                    model.setData(index, f"{value:.2f}", Qt.EditRole)
                    model.setData(index, f"{value:.2f}", Qt.UserRole + 2)

            elif field == "Volume Threshold":
                model.setData(index, f"{value:.2f}", Qt.EditRole)

            elif isinstance(editor, QDoubleSpinBox):
                model.setData(index, f"{value:.1f}", Qt.EditRole)

            else:
                # Integers
                model.setData(index, str(int(value)), Qt.EditRole)

        # --- 4. Text/Others ---
        else:
            text = editor.text()
            model.setData(index, text, Qt.EditRole)

        # Sync parent state
        widget = self.parent()
        if hasattr(widget, "sync_to_state"):
            widget.sync_to_state()


def make_row(defaults, overrides=None, row_type=STEP_TYPE, children=None):
    overrides = overrides or {}
    items = []
    magnet_checked = False

    for field in protocol_grid_fields:
        if row_type == GROUP_TYPE:
            allowed_group_fields = ALLOWED_group_fields
            
            if field in allowed_group_fields:
                value = overrides.get(field, defaults.get(field, ""))
            else:
                value = ""
        else:
            value = overrides.get(field, defaults.get(field, ""))
            
        item = PGCItem(str(value))

        if field == "Description":
            item.setData(row_type, ROW_TYPE_ROLE)
            for hidden_field in ["UID"]:
                if hidden_field in overrides:
                    item.setData(overrides[hidden_field], Qt.UserRole + 1000 + hash(hidden_field) % 1000)

        if row_type == STEP_TYPE and field in CHECKBOX_COLS:
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            
            value_str = str(value).strip().lower()
            checked = value_str in ("1", "true", "yes", "on")
            
            item.setData(Qt.Checked if checked else Qt.Unchecked, Qt.CheckStateRole)
            item.setText("")
            if field == "Magnet":
                magnet_checked = checked
        elif row_type == STEP_TYPE and field == "Magnet Height (mm)":
            item.setData(str(value), Qt.UserRole + 2)
            if not magnet_checked:
                item.setEditable(False)
                item.setText("")
            else:
                item.setEditable(True)
                stored_value = item.data(Qt.UserRole + 2)
                if stored_value is not None and stored_value != "":
                    item.setText(str(stored_value))
                else:
                    item.setText(str(value))
        elif row_type == STEP_TYPE and field == "Force":
            item.setEditable(False)
            item.setText("")
        elif row_type == STEP_TYPE and field in ("Max. Path Length", "Run Time"):
            item.setEditable(False)
        elif row_type == GROUP_TYPE:
            if field in ("Description", "Voltage", "Frequency", "Trail Length", "Repetitions"):
                item.setEditable(True)
            elif field in ("Duration", "Run Time", "ID"):
                item.setEditable(False)
            else:
                item.setEditable(False)
                item.setText("")
                if field in CHECKBOX_COLS:
                    item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
                    item.setData(None, Qt.CheckStateRole)
        elif row_type == STEP_TYPE and field == "ID":
            item.setEditable(False)

        items.append(item)

    if row_type == GROUP_TYPE and children:
        calculate_group_aggregation_from_children(items, children)

    return items

def calculate_group_aggregation_from_children(group_items, children):
    agg_fields = ["Voltage", "Frequency", "Trail Length"]
    agg_values = {field: None for field in agg_fields}
    agg_consistent = {field: True for field in agg_fields}
    agg_found = {field: False for field in agg_fields}

    total_duration = 0.0
    total_run_time = 0.0

    for child_row in children:
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

        except (ValueError, IndexError, AttributeError):
            pass

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
        rep_idx = protocol_grid_fields.index("Repetitions")
        try:
            group_reps = int(group_items[rep_idx].text() or "1")
        except ValueError:
            group_reps = 1
        group_items[dur_idx].setText(f"{total_duration * group_reps:.1f}")
        group_items[run_idx].setText(f"{total_run_time * group_reps:.2f}")
    except IndexError:
        pass
