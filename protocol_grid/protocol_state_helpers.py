from PySide6.QtCore import Qt

from protocol_grid.protocol_grid_helpers import make_row
from protocol_grid.consts import GROUP_TYPE, STEP_TYPE, ROW_TYPE_ROLE, step_defaults, group_defaults

def state_to_model(state, model):
    
    def add_items(parent, seq):
        for obj in seq:
            if obj.get("type") == GROUP_TYPE:
                group_data = {**group_defaults, **obj.get("parameters", {}), "Description": obj.get("name", "Group")}
                group_items = make_row(group_defaults, overrides=group_data, row_type=GROUP_TYPE)
                parent.appendRow(group_items)
                if "elements" in obj:
                    add_items(group_items[0], obj["elements"])
            elif obj.get("type") == STEP_TYPE:
                step_data = {**step_defaults, **obj.get("parameters", {}), "Description": obj.get("name", "Step")}
                step_items = make_row(step_defaults, overrides=step_data, row_type=STEP_TYPE)
                parent.appendRow(step_items)
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
                if item:
                    if item.item_type in ("Video", "Magnet"):
                        fields[item.item_type] = (
                            1 if item.data(Qt.CheckStateRole) == Qt.Checked
                            else 0
                        )
                    else:
                        fields[item.item_type] = item.text()
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
    state.notify_observers()

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

    
