from PySide6.QtCore import Qt
from protocol_grid.protocol_grid_helpers import make_row
from protocol_grid.state.protocol_state import ProtocolState, ProtocolStep, ProtocolGroup
from protocol_grid.consts import GROUP_TYPE, STEP_TYPE, group_defaults, step_defaults


class ModelBuilder:
    """
    Builds QTreeView models from ProtocolState.
    """
    
    def __init__(self, state: ProtocolState):
        self.state = state
        
    def build_model(self, model):
        model.clear()
        model.setHorizontalHeaderLabels(self.state.fields)
        self._add_items(model.invisibleRootItem(), self.state.sequence)
        
    def _add_items(self, parent, sequence):
        for obj in sequence:
            if isinstance(obj, ProtocolGroup):
                group_data = {**group_defaults, **obj.parameters, "Description": obj.name}
                
                # Collect children for aggregation
                child_items = []
                self._collect_child_items(child_items, obj.elements)
                
                group_items = make_row(group_defaults, overrides=group_data, 
                                     row_type=GROUP_TYPE, children=child_items)
                parent.appendRow(group_items)
                
                # Recursively add children
                self._add_items(group_items[0], obj.elements)
                
            elif isinstance(obj, ProtocolStep):
                step_data = {**step_defaults, **obj.parameters, "Description": obj.name}
                step_items = make_row(step_defaults, overrides=step_data, row_type=STEP_TYPE)
                parent.appendRow(step_items)
                
                # Store device state on the model item
                desc_item = step_items[0]
                desc_item.setData(obj.device_state, Qt.UserRole + 100)
                
    def _collect_child_items(self, child_items, sequence):
        """
        Collects child items for group aggregation calculations.
        """
        for obj in sequence:
            if isinstance(obj, ProtocolGroup):
                group_data = {**group_defaults, **obj.parameters, "Description": obj.name}
                sub_child_items = []
                self._collect_child_items(sub_child_items, obj.elements)
                group_items = make_row(group_defaults, overrides=group_data, 
                                     row_type=GROUP_TYPE, children=sub_child_items)
                child_items.append(group_items)
            elif isinstance(obj, ProtocolStep):
                step_data = {**step_defaults, **obj.parameters, "Description": obj.name}
                step_items = make_row(step_defaults, overrides=step_data, row_type=STEP_TYPE)
                child_items.append(step_items)