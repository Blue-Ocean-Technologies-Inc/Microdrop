import copy
from collections import defaultdict

from PySide6.QtCore import Qt

from protocol_grid.protocol_grid_helpers import make_row
from protocol_grid.state.protocol_state import ProtocolStep, ProtocolGroup
from protocol_grid.state.device_state import DeviceState
from protocol_grid.consts import GROUP_TYPE, STEP_TYPE, ROW_TYPE_ROLE, step_defaults, group_defaults, protocol_grid_fields

def make_test_steps():
    def make_electrode_dict(active_ids, total=120):
        return {str(i): (str(i) in active_ids) for i in range(total)}
    test_cases = [
        {"name": "No electrodes, no paths", "activated_electrodes": make_electrode_dict([]), "paths": []},
        {"name": "Some electrodes active, no paths", "activated_electrodes": make_electrode_dict(["5", "10", "50"]), "paths": []},
        {"name": "No electrodes, one path", "activated_electrodes": make_electrode_dict([]), "paths": [["1", "2", "3", "4"]]},
        {"name": "No electrodes, multiple paths", "activated_electrodes": make_electrode_dict([]), "paths": [["10", "11"], ["20", "21", "22", "23", "24"], ["30", "31", "32"]]},
        {"name": "Electrodes active, multiple paths", "activated_electrodes": make_electrode_dict(["2", "3", "4"]), "paths": [["5", "6", "7"], ["8", "9"]]},
        {"name": "Electrodes active, no paths", "activated_electrodes": make_electrode_dict(["1", "2"]), "paths": []},
        {"name": "Paths present, but all empty", "activated_electrodes": make_electrode_dict([]), "paths": [[], []]},
        {"name": "All electrodes active, no paths", "activated_electrodes": make_electrode_dict([str(i) for i in range(120)]), "paths": []},
    ]
    steps = []
    for case in test_cases:
        step = ProtocolStep(name=case["name"])
        step.device_state = DeviceState(case["activated_electrodes"], case["paths"])
        steps.append(step)
    return steps

def flatten_steps(sequence):
    for e in sequence:
        if isinstance(e, ProtocolStep):
            yield e
        elif isinstance(e, ProtocolGroup):
            yield from flatten_steps(e.elements)

def calculate_step_dev_fields(step, repetitions, duration, repeat_duration):
    max_path_length = step.device_state.longest_path_length()
    run_time = step.device_state.calculated_duration(duration, repetitions, repeat_duration)
    return max_path_length, run_time

def state_to_model(state, model):

    def add_items(parent, seq):
        for obj in seq:
            if isinstance(obj, ProtocolGroup):
                group_data = {**group_defaults, **obj.parameters, "Description": obj.name}
                # recursively build children
                child_items = []
                add_items_collect(child_items, obj.elements)
                group_items = make_row(group_defaults, overrides=group_data, row_type=GROUP_TYPE, children=child_items)
                parent.appendRow(group_items)
                add_items(group_items[0], obj.elements)
            elif isinstance(obj, ProtocolStep):
                step_data = {**step_defaults, **obj.parameters, "Description": obj.name}
                step_items = make_row(step_defaults, overrides=step_data, row_type=STEP_TYPE)
                parent.appendRow(step_items)

    def add_items_collect(child_items, seq):
        for obj in seq:
            if isinstance(obj, ProtocolGroup):
                group_data = {**group_defaults, **obj.parameters, "Description": obj.name}
                sub_child_items = []
                add_items_collect(sub_child_items, obj.elements)
                group_items = make_row(group_defaults, overrides=group_data, row_type=GROUP_TYPE, children=sub_child_items)
                child_items.append(group_items)
            elif isinstance(obj, ProtocolStep):
                step_data = {**step_defaults, **obj.parameters, "Description": obj.name}
                step_items = make_row(step_defaults, overrides=step_data, row_type=STEP_TYPE)
                child_items.append(step_items)
    if hasattr(model, 'clear') and hasattr(model, 'setHorizontalHeaderLabels'):
        model.clear()
        model.setHorizontalHeaderLabels(state.fields)
        add_items(model.invisibleRootItem(), state.sequence)
    else:
        add_items(model, state.sequence)

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
                        state_val = item.data(Qt.CheckStateRole)
                        if state_val is None:
                            val = item.data(Qt.ItemDataRole.EditRole)
                            if val in ("1", 1, True):
                                fields[field] = "1"
                            else:
                                fields[field] = "0"
                        else:
                            fields[field] = "1" if state_val == Qt.Checked else "0"
                        fields[field] = str(fields[field])
                    elif field == "Magnet Height":
                        last_value = item.data(Qt.UserRole + 2)
                        if last_value is not None and last_value != "":
                            fields[field] = str(last_value)
                        else:
                            fields[field] = item.text()
                    else:
                        fields[field] = item.text()
            if row_type == GROUP_TYPE:
                group_obj = ProtocolGroup(
                    parameters=fields,
                    name=name,
                    elements=parse_items(desc_item)
                )
                seq.append(group_obj)
            elif row_type == STEP_TYPE:
                step_obj = ProtocolStep(
                    parameters=fields,
                    name=name
                )
                device_state_data = desc_item.data(Qt.UserRole + 100)
                if isinstance(device_state_data, DeviceState):
                    step_obj.device_state = copy.deepcopy(device_state_data)
                seq.append(step_obj)
        return seq
    root = model.invisibleRootItem()
    state.sequence = parse_items(root)

def reassign_ids(model, protocol_state=None):
    """
    Assign hierarchical IDs:
    - Top-level groups: A, B, C, ...
    - Top-level steps: 1, 2, 3, ...
    - Children of group A: AA, AB, A1, A2, etc.
    - Children of group B: BA, BB, B1, B2, etc.
    - Children of group BA: BAA, BAB, BA1, BA2, etc.

    New: update device_state keys when protocol_state is provided.
    """

    def int_to_letters(n):
        result = ''
        while n > 0:
            n -= 1
            result = chr(65 + (n % 26)) + result
            n //= 26
        return result

    old_to_new_ids = {}

    def assign(parent, prefix=''):
        group_count = 1
        step_count = 1
        for row in range(parent.rowCount()):
            desc_item = parent.child(row, 0)
            id_item = parent.child(row, 1)
            row_type = desc_item.data(ROW_TYPE_ROLE)
            old_id = id_item.text()
            if row_type == GROUP_TYPE:
                group_id = (prefix + "_" if prefix else "") + int_to_letters(group_count)
                old_to_new_ids[old_id] = group_id
                id_item.setText(group_id)
                group_count += 1
                assign(desc_item, group_id)
            elif row_type == STEP_TYPE:
                step_id = (prefix + "_" if prefix else "") + str(step_count)
                old_to_new_ids[old_id] = step_id
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
    
def import_flat_protocol(flat_json):
    steps = flat_json["steps"]
    groups = {g["ID"]: g.get("Description", g.get("description", "")) for g in flat_json.get("groups", [])}
    fields = flat_json.get("fields", [])
    group_ids = set(groups.keys())

    def get_parent_id(step_id):
        return "_".join(step_id.split("_")[:-1]) if "_" in step_id else ""

    def parse_steps(step_list, parent_prefix="", depth=0, index=0):
        elements = []
        i = index - 1 if index > 0 else 0
        indent = "  " * depth
        while i < len(step_list):
            step = step_list[i]
            step_id = step["ID"]
            parent_id = get_parent_id(step_id)
            print("step_id, parent_id: ", step_id, ", ", parent_id)

            is_group = parent_id in group_ids
            if is_group:
                print(f"{indent}[GROUP] Creating group '{groups[parent_id]}' (ID: {parent_id}) at index {i}")
                group_steps = []
                j = i + 1 - index
                while j < len(step_list):
                    next_step = step_list[j - 1]
                    next_parent_id = get_parent_id(next_step["ID"])
                    print("next_parent_id for step_id(", next_step["ID"],"): ", next_parent_id)
                    print(next_parent_id == parent_id)
                    if next_parent_id == parent_id:
                        group_steps.append(next_step)
                        j += 1
                    else:
                        break
                print("number of steps under group(", parent_id, "): ", len(group_steps), ", j = ", j)
                print("calling parse_seq recursively")
                group_ids.remove(parent_id)
                group_elements = parse_steps(steps, parent_prefix=parent_id, depth=depth+1, index=i + 1)
                group = ProtocolGroup(
                    parameters={"Description": groups[parent_id]},
                    name=groups[parent_id],
                    elements=group_elements
                )
                elements.append(group)
            else:
                if parent_id == parent_prefix:
                    print(f"{indent}[STEP] Adding step '{step.get('Description', '')}' (ID: {step_id}) at index {i}")
                    params = {k: v for k, v in step.items() if k not in ("device_state",)}
                    step_obj = ProtocolStep(parameters=params, name=step.get("Description", "Step"))
                    if "device_state" in step:
                        step_obj.device_state.from_dict(step["device_state"])
                    elements.append(step_obj)
                i += 1
        return elements

    sequence = parse_steps(steps)
    print("==== DEBUG: Final sequence ====")
    def print_tree(elements, depth=0):
        for e in elements:
            if hasattr(e, "elements"):
                print("  " * depth + f"[GROUP] {getattr(e, 'name', '')}")
                print_tree(e.elements, depth+1)
            else:
                print("  " * depth + f"[STEP] {getattr(e, 'parameters', {}).get('Description', '')} ({getattr(e, 'parameters', {}).get('ID', '')})")
    print_tree(sequence)
    return sequence, fields