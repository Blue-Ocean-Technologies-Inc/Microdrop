import copy
from protocol_grid.consts import protocol_grid_fields
from protocol_grid.state.device_state import DeviceState

class ProtocolStep:
    def __init__(self, parameters=None, name="Step"):
        self.name = name
        self.parameters = parameters or {}
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

    def to_json(self):
        return self.to_dict()
    
    def from_json(self, data: dict):
        self.from_dict(data)

    def snapshot_for_undo(self):
        print("SNAPSHOT: sequence length =", len(self.sequence))
        snap = copy.deepcopy((self.sequence, list(self.fields)))
        print("SNAPSHOT: id(self.sequence) =", id(self.sequence), "id(snap[0]) =", id(snap[0]))
        if self.sequence:
            print("SNAPSHOT: id(self.sequence[0]) =", id(self.sequence[0]), "id(snap[0][0]) =", id(snap[0][0]))
        self.undo_stack.append(snap)
        print("UNDO STACK SIZE:", len(self.undo_stack))
        if len(self.undo_stack) > 20:
            self.undo_stack = self.undo_stack[-20:]
        self.redo_stack.clear()        

    def undo(self):
        print("UNDO called. Undo stack size:", len(self.undo_stack))
        if not self.undo_stack:
            print("UNDO: Nothing to undo.")
            return
        current = copy.deepcopy((self.sequence, list(self.fields)))
        self.redo_stack.append(current)
        print("Before undo: id(self.sequence) =", id(self.sequence))
        last = self.undo_stack.pop()
        self.sequence, self.fields = copy.deepcopy(last)
        print("After undo: id(self.sequence) =", id(self.sequence))
        print("UNDO: sequence length after undo =", len(self.sequence))

    def redo(self):
        print("REDO called. Redo stack size:", len(self.redo_stack))
        if not self.redo_stack:
            print("REDO: Nothing to redo.")
            return
        current = copy.deepcopy((self.sequence, list(self.fields)))
        self.undo_stack.append(current)
        next_ = self.redo_stack.pop()
        self.sequence, self.fields = copy.deepcopy(next_)
        print("REDO: sequence length after redo =", len(self.sequence))