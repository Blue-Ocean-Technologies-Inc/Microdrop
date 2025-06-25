from PySide6.QtCore import Qt

from protocol_grid.protocol_grid_helpers import make_row
from protocol_grid.consts import GROUP_TYPE, STEP_TYPE, ROW_TYPE_ROLE, step_defaults, group_defaults, protocol_grid_fields

def state_to_model(state, model):

    def add_items(parent, seq):
        for obj in seq:
            if obj.get("type") == GROUP_TYPE:
                group_data = {**group_defaults, **obj.get("parameters", {}), "Description": obj.get("name", "Group")}
                # build children first, for aggregation
                child_items = []
                if "elements" in obj:
                    for child_obj in obj["elements"]:
                        if child_obj.get("type") == GROUP_TYPE:
                            # build children recursively, dont add to model yet
                            sub_child_items = []
                            add_items_collect(sub_child_items, [child_obj])
                            child_items.extend(sub_child_items)
                        elif child_obj.get("type") == STEP_TYPE:
                            step_data = {**step_defaults, **child_obj.get("parameters", {}), "Description": child_obj.get("name", "Step")}
                            step_items = make_row(step_defaults, overrides=step_data, row_type=STEP_TYPE)
                            child_items.append(step_items)
                group_items = make_row(group_defaults, overrides=group_data, row_type=GROUP_TYPE, children=child_items)
                parent.appendRow(group_items)
                # now add children to model
                if "elements" in obj:
                    add_items(group_items[0], obj["elements"])
            elif obj.get("type") == STEP_TYPE:
                step_data = {**step_defaults, **obj.get("parameters", {}), "Description": obj.get("name", "Step")}
                step_items = make_row(step_defaults, overrides=step_data, row_type=STEP_TYPE)
                parent.appendRow(step_items)

    def add_items_collect(child_items, seq):
        for obj in seq:
            if obj.get("type") == GROUP_TYPE:
                group_data = {**group_defaults, **obj.get("parameters", {}), "Description": obj.get("name", "Group")}
                sub_child_items = []
                if "elements" in obj:
                    add_items_collect(sub_child_items, obj["elements"])
                group_items = make_row(group_defaults, overrides=group_data, row_type=GROUP_TYPE, children=sub_child_items)
                child_items.append(group_items)
            elif obj.get("type") == STEP_TYPE:
                step_data = {**step_defaults, **obj.get("parameters", {}), "Description": obj.get("name", "Step")}
                step_items = make_row(step_defaults, overrides=step_data, row_type=STEP_TYPE)
                child_items.append(step_items)

    model.clear()
    model.setHorizontalHeaderLabels(state.fields)
    add_items(model.invisibleRootItem(), state.sequence)

def model_to_state(model, state):

    def parse_items(parent_item):
        seq = []
        for row in range(parent_item.rowCount()):
            desc_item = parent_item.child(row, 0)
            row_type = desc_item.data(ROW_TYPE_ROLE)
            name = desc_item.text()
            fields = {}
            for col in range(parent_item.columnCount()):
                item = parent_item.child(row, col)
                field = protocol_grid_fields[col]
                if item:
                    if field in ("Video", "Magnet"):
                        state = item.data(Qt.CheckStateRole)
                        fields[field] = "1" if state == Qt.Checked else "0"
                    else:
                        fields[field] = item.text()
            if row_type == GROUP_TYPE:
                group_obj = {
                    "type": GROUP_TYPE,
                    "name": name,
                    "parameters": fields,
                    "elements": parse_items(desc_item)
                }
                seq.append(group_obj)
            elif row_type == STEP_TYPE:
                step_obj = {
                    "type": STEP_TYPE,
                    "name": name,
                    "parameters": fields
                }
                seq.append(step_obj)
        return seq
    root = model.invisibleRootItem()
    state.sequence = parse_items(root)

def reassign_ids(model):
    """
    Assign hierarchical IDs:
    - Top-level groups: A, B, C, ...
    - Top-level steps: 1, 2, 3, ...
    - Children of group A: AA, AB, A1, A2, etc.
    - Children of group B: BA, BB, B1, B2, etc.
    - Children of group BA: BAA, BAB, BA1, BA2, etc.
    """

    def int_to_letters(n):
        result = ''
        while n > 0:
            n -= 1
            result = chr(65 + (n % 26)) + result
            n //= 26
        return result

    def assign(parent, prefix=''):
        group_count = 1
        step_count = 1
        for row in range(parent.rowCount()):
            desc_item = parent.child(row, 0)
            id_item = parent.child(row, 1)
            row_type = desc_item.data(ROW_TYPE_ROLE)
            if row_type == GROUP_TYPE:
                group_id = (prefix + "_" if prefix else "") + int_to_letters(group_count)
                id_item.setText(group_id)
                group_count += 1
                assign(desc_item, group_id)
            elif row_type == STEP_TYPE:
                step_id = (prefix + "_" if prefix else "") + str(step_count)
                id_item.setText(step_id)
                step_count += 1

    assign(model.invisibleRootItem())

def clamp_trail_overlay(parent):
    """
    Ensure that the Trail Overlay value is not greater than Trail Length - 1 for all steps.
    """
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

    
