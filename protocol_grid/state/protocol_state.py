from typing import List, Dict, Any, Optional, Callable
import copy

class ProtocolState:
    def __init__(self):
        self.sequence: List[Dict[str, Any]] = []
        self.fields: List[str] = []
        self.field_registry: Dict[str, Dict[str, Any]] = {}

        self.undo_stack: List[Any] = []
        self.redo_stack: List[Any] = []

        self._observers: List[Callable] = []

    def add_observer(self, cb: Callable):
        if cb not in self._observers:
            self._observers.append(cb)
    
    def remove_observer(self, cb: Callable):
        if cb in self._observers:
            self._observers.remove(cb) 

    def notify_observers(self):
        for cb in self._observers:
            cb()

    def register_field(self, field: str, metadata: Optional[Dict[str, Any]]=None):
        if field not in self.fields:
            self.fields.append(field)
        if metadata:
            self.field_registry[field] = metadata
        self.notify_observers()

    def unregister_field(self, field: str):
        if field in self.fields:
            self.fields.remove(field)
        self.field_registry.pop(field, None)
        self.notify_observers()

    def clear(self):
        self.sequence = []
        self.notify_observers()

    def snapshot_for_undo(self):
        self.undo_stack.append(copy.deepcopy((self.sequence, list(self.fields))))
        if len(self.undo_stack) > 6:
            self.undo_stack = self.undo_stack[-6:]
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack:
            return
        current = copy.deepcopy((self.sequence, list(self.fields)))
        self.redo_stack.append(current)
        last = self.undo_stack.pop()
        self.sequence, self.fields = copy.deepcopy(last)
        self.notify_observers()

    def redo(self):
        if not self.redo_stack:
            return
        current = copy.deepcopy((self.sequence, list(self.fields)))
        self.undo_stack.append(current)
        next_ = self.redo_stack.pop()
        self.sequence, self.fields = copy.deepcopy(next_)
        self.notify_observers()

    def to_json(self):
        return{
            "sequence": self.sequence, 
            "fields": self.fields,
        }
    
    def from_json(self, data: dict):
        self.sequence = data.get("sequence", [])
        self.fields = data.get("fields", [])
        self.notify_observers()