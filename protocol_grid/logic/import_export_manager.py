from protocol_grid.state.protocol_state import ProtocolState, ProtocolStep, ProtocolGroup
from protocol_grid.state.device_state import DeviceState


class ImportExportManager:
    
    @staticmethod
    def import_flat_protocol(flat_json):
        steps = flat_json["steps"]
        groups_meta = {
            g["ID"]: {
                "Description": g.get("Description", g.get("description", "")),
                "Repetitions": g.get("Repetitions", "1")
            }
            for g in flat_json.get("groups", [])
        }       
        fields = flat_json.get("fields", [])
        group_objs = {}

        def get_parent_group_id(step_id):
            parts = step_id.split("_")
            if len(parts) == 1:
                return None
            return "_".join(parts[:-1]) 
        
        def get_or_create_group(group_id):
            if group_id in group_objs:
                return group_objs[group_id]
            parent_id = get_parent_group_id(group_id)
            meta = groups_meta.get(group_id, {})
            group = ProtocolGroup(
                parameters={
                    "Description": meta.get("Description", group_id),
                    "ID": group_id,
                    "Repetitions": meta.get("Repetitions", "1")
                },
                name=meta.get("Description", group_id),
                elements=[]
            )
            group_objs[group_id] = group
            if parent_id:
                parent_group = get_or_create_group(parent_id)
                parent_group.elements.append(group)
            return group

        steps_by_id = {step["ID"]: step for step in steps}
        groups_by_id = {g["ID"]: g for g in flat_json.get("groups", [])}
        combined = []
        step_ids = set()
        group_ids = set()
        for step in steps:
            combined.append(step)
            step_ids.add(step["ID"])
        for group in flat_json.get("groups", []):
            combined.append(("group", group["ID"]))
            group_ids.add(group["ID"])

        root_sequence = []
        inserted_groups = set()

        def insert_group_in_parent(group_id):
            if group_id in inserted_groups:
                return
            group = get_or_create_group(group_id)
            parent_id = get_parent_group_id(group_id)
            if parent_id is None:
                if group not in root_sequence:
                    root_sequence.append(group)
            inserted_groups.add(group_id)            

        for step in steps:
            step_id = step["ID"]
            parent_group_id = get_parent_group_id(step_id)
            params = {k: v for k, v in step.items() if k != "device_state"}
            step_obj = ProtocolStep(
                parameters=params,
                name=step.get("Description", "Step")
            )
            if "device_state" in step:
                step_obj.device_state.from_dict(step["device_state"])
            if parent_group_id:
                group = get_or_create_group(parent_group_id)
                group.elements.append(step_obj)
                insert_group_in_parent(parent_group_id)
            else:
                root_sequence.append(step_obj)
            
        for group in flat_json.get("groups", []):
            group_id = group["ID"]
            insert_group_in_parent(group_id)

        return root_sequence, fields