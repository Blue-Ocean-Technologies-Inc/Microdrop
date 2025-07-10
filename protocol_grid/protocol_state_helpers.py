from protocol_grid.state.protocol_state import ProtocolStep, ProtocolGroup
from protocol_grid.state.device_state import DeviceState
from protocol_grid.consts import GROUP_TYPE, STEP_TYPE, ROW_TYPE_ROLE, step_defaults, group_defaults, protocol_grid_fields

def flatten_protocol_for_run(protocol_state):
    """
    Returns a list of dicts:
    {
        "step": ProtocolStep,
        "path": [int, ..],  # path in the tree
        "rep_idx": int,      # current repetition (1-based)
        "rep_total": int     # total repetitions for this step
    }
    """
    run_order = []

    def recurse(elements, path_prefix, group_reps=1):
        for idx, element in enumerate(elements):
            path = path_prefix + [idx]
            if hasattr(element, "parameters"):
                reps = int(element.parameters.get("Repetitions", 1) or 1)
            else:
                reps = 1
            if hasattr(element, "elements"):
                for g_rep in range(reps):
                    recurse(element.elements, path, group_reps * reps)
            else:
                for s_rep in range(reps):
                    run_order.append({
                        "step": element,
                        "path": path,
                        "rep_idx": s_rep + 1,
                        "rep_total": reps
                    })
    recurse(protocol_state.sequence, [])
    return run_order

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


def reassign_ids(model, protocol_state=None):
    """
    Assign hierarchical IDs:
    - Top-level groups: A, B, C, ...
    - Top-level steps: 1, 2, 3, ...
    - Children of group A: A_A, A_B, A_1, A_2, etc.
    - Children of group B: B_A, B_B, B_1, B_2, etc.
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


def state_to_model(state, model):
    """
    DEPRECATED: Use StateManager.sync_state_to_model() instead.
    """
    from protocol_grid.view.model_builder import ModelBuilder
    builder = ModelBuilder(state)
    builder.build_model(model)

def model_to_state(model, state):
    """
    DEPRECATED: Use StateManager.sync_model_to_state() instead.
    """
    from protocol_grid.state.state_manager import StateManager
    manager = StateManager(state)
    manager.sync_model_to_state(model)