from protocol_grid.protocol_grid_helpers import make_row, int_to_letters
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
                    if item.item_type == "Video":
                        fields[item.item_type] = (
                            1 if item.data(2) == 2 else 0  # Qt.Checked == 2
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
    step_id = 1
    group_id = 1
    def reassign(parent):
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
                reassign(desc_item)
    reassign(model.invisibleRootItem())

    
