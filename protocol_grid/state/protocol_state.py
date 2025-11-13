import copy

from PySide6.QtCore import Qt

from protocol_grid.consts import protocol_grid_fields
from protocol_grid.state.device_state import DeviceState

class ProtocolStep:
    def __init__(self, parameters=None, name="Step"):
        self.name = name
        self.parameters = parameters or {}
        
        # ensure Force field exists (backwards compatibility)
        if "Force" not in self.parameters:
            self.parameters["Force"] = ""
        
        # normalize checkbox fields for consistent storage
        for field in ("Magnet", "Video", "Capture", "Record"):
            if field in self.parameters:
                val = self.parameters[field]
                if isinstance(val, bool):
                    self.parameters[field] = "1" if val else "0"
                elif isinstance(val, int):
                    self.parameters[field] = "1" if val in (1, 2, Qt.Checked) else "0"
                elif isinstance(val, str):
                    self.parameters[field] = "1" if val.strip().lower() in ("1", "true", "yes", "on") else "0"
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
        
        # ensure Force field exists (backwards compatibility)
        if "Force" not in self.parameters:
            self.parameters["Force"] = ""

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
        self._uid_counter = 1

        # calibration data storage
        self._liquid_capacitance_over_area = None
        self._filler_capacitance_over_area = None

    def get_next_uid(self):
        uid = self._uid_counter
        self._uid_counter += 1
        return uid

    def update_uid_counter_from_sequence(self):
        max_uid = 0
        
        def find_max_uid(elements):
            nonlocal max_uid
            for element in elements:
                if isinstance(element, ProtocolStep):
                    uid_str = element.parameters.get("UID", "0")
                    try:
                        uid = int(uid_str) if uid_str else 0
                        max_uid = max(max_uid, uid)
                    except ValueError:
                        pass
                elif isinstance(element, ProtocolGroup):
                    find_max_uid(element.elements)
        
        find_max_uid(self.sequence)
        self._uid_counter = max_uid + 1

    def assign_uid_to_step(self, step):
        if not step.parameters.get("UID"):
            step.parameters["UID"] = str(self.get_next_uid())

    def assign_uids_to_all_steps(self):
        def assign_recursive(elements):
            for element in elements:
                if isinstance(element, ProtocolStep):
                    self.assign_uid_to_step(element)
                elif isinstance(element, ProtocolGroup):
                    assign_recursive(element.elements)
        
        assign_recursive(self.sequence)

    def get_protocol_id_to_channel_mapping(self):

        def find_mapping_recursive(elements):
            for element in elements:
                if isinstance(element, ProtocolStep):
                    if element.device_state and element.device_state.id_to_channel:
                        return element.device_state.id_to_channel
                elif isinstance(element, ProtocolGroup):
                    mapping = find_mapping_recursive(element.elements)
                    if mapping:
                        return mapping
            return {}
        
        return find_mapping_recursive(self.sequence)

    def set_protocol_id_to_channel_mapping(self, id_to_channel_mapping):

        def apply_mapping_recursive(elements):
            for element in elements:
                if isinstance(element, ProtocolStep):
                    if not element.device_state:
                        element.device_state = DeviceState()
                    element.device_state.id_to_channel = id_to_channel_mapping.copy()
                elif isinstance(element, ProtocolGroup):
                    apply_mapping_recursive(element.elements)
        
        apply_mapping_recursive(self.sequence)

    def _ensure_force_field_in_sequence(self):
        """ensure Force field exists (backwards compatibility)"""
        def ensure_force_recursive(elements):
            for element in elements:
                if isinstance(element, (ProtocolStep, ProtocolGroup)):
                    if "Force" not in element.parameters:
                        element.parameters["Force"] = ""
                if isinstance(element, ProtocolGroup):
                    ensure_force_recursive(element.elements)
        
        ensure_force_recursive(self.sequence)

    def to_dict(self):
        protocol_id_to_channel = self.get_protocol_id_to_channel_mapping()
        
        return {
            "sequence": [step.to_dict() for step in self.sequence],
            "fields": self.fields,
            "id_to_channel": protocol_id_to_channel,
            "_uid_counter": self._uid_counter,
            "_liquid_capacitance_over_area": self._liquid_capacitance_over_area,
            "_filler_capacitance_over_area": self._filler_capacitance_over_area,
        }
    
    def from_dict(self, data):
        self.sequence = []
        for e in data.get("sequence", []):
            if e.get("type") == "step":
                self.sequence.append(ProtocolStep.from_dict(e))
            elif e.get("type") == "group":
                self.sequence.append(ProtocolGroup.from_dict(e))
        self.fields = data.get("fields", list(protocol_grid_fields))
        self._uid_counter = data.get("_uid_counter", 1)

        # NEW: Load calibration data
        self._liquid_capacitance_over_area = data.get("_liquid_capacitance_over_area")
        self._filler_capacitance_over_area = data.get("_filler_capacitance_over_area")

        self.update_uid_counter_from_sequence()
        
        # ensure Force field exists (backwards compatibility)
        self._ensure_force_field_in_sequence()
        
        # apply id_to_channel mapping to all steps
        protocol_id_to_channel = data.get("id_to_channel", {})
        if protocol_id_to_channel:
            self.set_protocol_id_to_channel_mapping(protocol_id_to_channel)

    def to_flat_export(self):
        """
        Returns a dict with:
        - 'steps': list of step dicts (including device_state without id_to_channel)
        - 'groups': list of {'ID': group_id, 'Description': group_description}
        - 'fields': list of field names
        - 'id_to_channel': common mapping for all steps
        """
        steps = []
        groups = []
        
        protocol_id_to_channel = self.get_protocol_id_to_channel_mapping()

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
            "fields": list(self.fields),
            "id_to_channel": protocol_id_to_channel,
            "_uid_counter": self._uid_counter
        }
    
    def from_flat_export(self, flat_json):  
        from protocol_grid.logic.import_export_manager import ImportExportManager      
        sequence, fields = ImportExportManager.import_flat_protocol(flat_json)
        self.sequence = sequence
        self.fields = fields
        self._uid_counter = flat_json.get("_uid_counter", 1)
        self.update_uid_counter_from_sequence()
        
        # ensure Force field exists (backwards compatibility)
        self._ensure_force_field_in_sequence()
        
        # apply id_to_channel mapping to all steps
        protocol_id_to_channel = flat_json.get("id_to_channel", {})
        if protocol_id_to_channel:
            self.set_protocol_id_to_channel_mapping(protocol_id_to_channel)

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

    def set_calibration_data(self, liquid_capacitance_over_area, filler_capacitance_over_area):
        """Store calibration data"""
        self._liquid_capacitance_over_area = liquid_capacitance_over_area
        self._filler_capacitance_over_area = filler_capacitance_over_area

    def get_calibration_data(self):
        """Get stored calibration data."""
        return {
            'liquid_capacitance_over_area': self._liquid_capacitance_over_area,
            'filler_capacitance_over_area': self._filler_capacitance_over_area,
        }

    def has_complete_calibration_data(self):
        """Check if all required calibration data is available for force calculations."""
        return (self._liquid_capacitance_over_area is not None and 
                self._filler_capacitance_over_area is not None and
                self._liquid_capacitance_over_area >= 0 and 
                self._filler_capacitance_over_area >= 0)

    def get_element_by_path(self, path):
        path_dims = len(path)

        protocol_element = self.sequence[path[0]]

        if path_dims == 1:
            return protocol_element

        else:
            for idx in path[1:]:
                if isinstance(protocol_element, ProtocolGroup):
                    protocol_element = protocol_element.elements[idx]

                else:
                    raise Warning("Protocol group element not found. Multi Dim path not processed.")

            return protocol_element
