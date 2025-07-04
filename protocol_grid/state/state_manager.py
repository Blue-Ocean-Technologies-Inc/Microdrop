from PySide6.QtCore import Qt
from protocol_grid.state.protocol_state import ProtocolState
from protocol_grid.state.device_state import DeviceState
from protocol_grid.consts import protocol_grid_fields, GROUP_TYPE, STEP_TYPE, ROW_TYPE_ROLE


class StateManager:
    """
    Manages synchronization between UI model and protocol state.
    Ensures immediate state updates and proper validation.
    """
    
    def __init__(self, state: ProtocolState):
        self.state = state
        
    def sync_model_to_state(self, model):
        """
        Synchronizes the QTreeView model to the protocol state.
        Called after every UI change to ensure immediate state updates.
        """
        steps = []
        groups = []
        
        def parse_items(parent_item, prefix=""):
            group_counter = 1
            step_counter = 1
            
            for row in range(parent_item.rowCount()):
                desc_item = parent_item.child(row, 0)
                if not desc_item:
                    continue
                    
                row_type = desc_item.data(ROW_TYPE_ROLE)
                name = desc_item.text()
                
                fields = {}
                for col in range(len(protocol_grid_fields)):
                    item = parent_item.child(row, col)
                    field = protocol_grid_fields[col]
                    if item:
                        if field in ("Video", "Magnet"):
                            state_val = item.data(Qt.CheckStateRole)
                            if state_val is None:
                                val = item.data(Qt.ItemDataRole.EditRole)
                                fields[field] = "1" if val in ("1", 1, True) else "0"
                            else:
                                fields[field] = "1" if state_val == Qt.Checked or state_val == 2 else "0"
                        elif field == "Magnet Height":
                            last_value = item.data(Qt.UserRole + 2)
                            if last_value is not None and last_value != "":
                                fields[field] = str(last_value)
                            else:
                                fields[field] = item.text()
                        else:
                            fields[field] = item.text()
                
                if row_type == GROUP_TYPE:
                    group_id = (prefix + "_" if prefix else "") + chr(64 + group_counter)
                    groups.append({
                        "ID": group_id,
                        "Description": fields.get("Description", name)
                    })
                    parse_items(desc_item, group_id)
                    group_counter += 1
                    
                elif row_type == STEP_TYPE:
                    step_id = (prefix + "_" if prefix else "") + str(step_counter)
                    step_dict = dict(fields)
                    step_dict["ID"] = step_id
                    
                    device_state_data = desc_item.data(Qt.UserRole + 100)
                    if isinstance(device_state_data, DeviceState):
                        step_dict["device_state"] = device_state_data.to_dict()
                    else:
                        step_dict["device_state"] = DeviceState().to_dict()
                    
                    steps.append(step_dict)
                    step_counter += 1
        
        parse_items(model.invisibleRootItem())
        
        flat_data = {
            "steps": steps,
            "groups": groups,
            "fields": self.state.fields
        }
        self.state.from_flat_export(flat_data)
        
    def sync_state_to_model(self, model):
        """
        Synchronizes the protocol state to the QTreeView model.
        Completely rebuilds the model from state.
        """
        from protocol_grid.view.model_builder import ModelBuilder
        builder = ModelBuilder(self.state)
        builder.build_model(model)
