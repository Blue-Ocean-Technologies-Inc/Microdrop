from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any, Tuple, Union, TYPE_CHECKING
import json


# Define the Step model
class ProtocolStep(BaseModel):
    idx: List[int] = [0]
    name: str
    parameters: Dict[str, Any]


# Define the Group model
class ProtocolGroup(BaseModel):
    group_idx: List[int] = [0]
    name: str

    elements: Optional[List[Union[ProtocolStep, 'ProtocolGroup']]] = Field(default_factory=list)

    def __init__(self, **data):
        super().__init__(**data)

    @property
    def idx(self):
        return self.group_idx

    @idx.setter
    def idx(self, value):
        self.group_idx = value

        # this group has been added to a super group. update its subgroups, and steps to reflect the new structure
        for element in self.elements:
            element.idx = self.idx + element.idx[:-1]

    def add_element(self, new_element: [ProtocolStep, 'ProtocolGroup']):
        new_element.idx = self.idx + [len(self.elements)]
        self.elements.append(new_element)

    def get_element(self, element_idx: str):
        for element in self.elements:
            # Direct match
            if element.idx == element_idx:
                return element

            # Recurse into subgroups
            elif isinstance(element, ProtocolGroup):
                sub_element = element.get_element(element_idx)
                if sub_element is not None:
                    return sub_element

        # If we never returned, the element was not found
        return None
