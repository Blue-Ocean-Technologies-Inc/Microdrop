import copy
from protocol_grid.consts import protocol_grid_fields
from protocol_grid.state.device_state import DeviceState

class ProtocolStep:
    def __init__(self, parameters=None, name="Step"):
        self.name = name
        self.parameters = parameters or {}
        for field in ("Magnet", "Video"):
            if field in self.parameters:
                val = self.parameters[field]
                if str(val).strip().lower() in ("1", "true", "yes", "on"):
                    self.parameters[field] = "1"
                else:
                    self.parameters[field] = "0"        
        
        self.device_state = DeviceState()

    def to_dict(self):
        return {
            "type": "step",
            "name": self.name,
            "parameters": self.parameters,
            "device_state": self.device_state.to_dict()
        }

    @classmethod
    def from_dict(cls, data):
        obj = cls(parameters=data.get("parameters", {}), name=data.get("name", "Step"))
        obj.device_state.from_dict(data.get("device_state", {}))
        return obj


class ProtocolGroup:
    def __init__(self, parameters=None, name="Group", elements=None):
        self.name = name
        self.parameters = parameters or {}
        self.elements = elements or []

    def to_dict(self):
        return {
            "type": "group",
            "name": self.name,
            "parameters": self.parameters,
            "elements": [e.to_dict() for e in self.elements]
        }

    @classmethod
    def from_dict(cls, data):
        elements = [ProtocolStep.from_dict(e) if e.get("type") == "step" else ProtocolGroup.from_dict(e)
                    for e in data.get("elements", [])]
        return cls(parameters=data.get("parameters", {}), name=data.get("name", "Group"), elements=elements)


class ProtocolState:
    def __init__(self, sequence=None):
        self.sequence = sequence if sequence is not None else []
        self.fields = list(protocol_grid_fields)
        self.undo_stack = []
        self.redo_stack = []

    def to_dict(self):
        return {
            "sequence": [step.to_dict() for step in self.sequence],
            "fields": self.fields
        }
    
    def from_dict(self, data):
        self.sequence = []
        for e in data.get("sequence", []):
            if e.get("type") == "step":
                self.sequence.append(ProtocolStep.from_dict(e))
            elif e.get("type") == "group":
                self.sequence.append(ProtocolGroup.from_dict(e))
        self.fields = data.get("fields", list(protocol_grid_fields))

    def to_flat_export(self):
        """
        Returns a dict with:
        - 'steps': list of step dicts (including device_state as a dict)
        - 'groups': list of {'ID': group_id, 'Description': group_description}
        - 'fields': list of field names
        """
        steps = []
        groups = []

        def recurse(seq, prefix=""):
            group_counter = 1
            step_counter = 1
            for obj in seq:
                if isinstance(obj, ProtocolGroup):
                    group_id = (prefix + "_" if prefix else "") + chr(64 + group_counter)
                    groups.append({
                        "ID": group_id,
                        "Description": obj.parameters.get("Description", obj.name),
                        "Repetitions": obj.parameters.get("Repetitions", "1")
                    })
                    recurse(obj.elements, group_id)
                    group_counter += 1
                elif isinstance(obj, ProtocolStep):
                    step_id = (prefix + "_" if prefix else "") + str(step_counter)
                    step_dict = dict(obj.parameters)
                    step_dict["ID"] = step_id
                    step_dict["device_state"] = obj.device_state.to_dict() if hasattr(obj.device_state, "to_dict") else {}
                    steps.append(step_dict)
                    step_counter += 1

        recurse(self.sequence)
        return {
            "steps": steps,
            "groups": groups,
            "fields": list(self.fields)
        }
    
    def from_flat_export(self, flat_json):  
        from protocol_grid.logic.import_export_manager import ImportExportManager      
        sequence, fields = ImportExportManager.import_flat_protocol(flat_json)
        self.sequence = sequence
        self.fields = fields

    def to_json(self):
        return self.to_dict()
    
    def from_json(self, data: dict):
        self.from_dict(data)

    def snapshot_for_undo(self, programmatic=False):
        snap = copy.deepcopy(self.to_dict())
        self.undo_stack.append(snap)
        if len(self.undo_stack) > 20000:
            self.undo_stack = self.undo_stack[-20000:]
        if not programmatic:
            self.redo_stack.clear()        

    def undo(self):
        if not self.undo_stack:
            return
        current = copy.deepcopy(self.to_dict())
        self.redo_stack.append(current)
        last = self.undo_stack.pop()
        self.from_dict(last)

    def redo(self):
        if not self.redo_stack:
            return
        current = copy.deepcopy(self.to_dict())
        self.undo_stack.append(current)
        next_ = self.redo_stack.pop()
        self.from_dict(next_)