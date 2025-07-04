from protocol_grid.state.protocol_state import ProtocolState, ProtocolStep, ProtocolGroup
from protocol_grid.state.device_state import DeviceState


class ImportExportManager:
    
    @staticmethod
    def import_flat_protocol(flat_json):
        steps = flat_json["steps"]
        groups = {g["ID"]: g.get("Description", g.get("description", "")) for g in flat_json.get("groups", [])}
        fields = flat_json.get("fields", [])
        group_ids = set(groups.keys())

        def get_parent_id(step_id):
            return "_".join(step_id.split("_")[:-1]) if "_" in step_id else ""

        def parse_steps(step_list, parent_prefix="", depth=0):
            elements = []
            i = 0
            
            while i < len(step_list):
                step = step_list[i]
                step_id = step["ID"]
                parent_id = get_parent_id(step_id)
                
                # Only process steps whose parent matches current prefix
                if parent_id != parent_prefix:
                    i += 1
                    continue
                
                # Check if we need to create a group for steps with this parent
                if parent_id in group_ids and parent_id not in [g.parameters.get("ID", "") for g in elements if isinstance(g, ProtocolGroup)]:
                    # Create group and collect all its children
                    group_steps = []
                    j = i
                    while j < len(step_list):
                        next_step = step_list[j]
                        next_parent_id = get_parent_id(next_step["ID"])
                        if next_parent_id == parent_id:
                            group_steps.append(next_step)
                            j += 1
                        else:
                            break
                    
                    # Recursively parse group children
                    group_elements = parse_steps(group_steps, parent_prefix=parent_id, depth=depth+1)
                    group = ProtocolGroup(
                        parameters={"Description": groups[parent_id], "ID": parent_id},
                        name=groups[parent_id],
                        elements=group_elements
                    )
                    elements.append(group)
                    i = j  # Skip processed steps
                else:
                    # Regular step
                    params = {k: v for k, v in step.items() if k not in ("device_state",)}
                    step_obj = ProtocolStep(parameters=params, name=step.get("Description", "Step"))
                    
                    # Set device state
                    if "device_state" in step:
                        step_obj.device_state.from_dict(step["device_state"])
                    
                    elements.append(step_obj)
                    i += 1
            
            return elements

        sequence = parse_steps(steps)
        return sequence, fields