from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union


class ProtocolStep(BaseModel):
    name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ProtocolGroup(BaseModel):
    name: str
    elements: List[Union['ProtocolStep', 'ProtocolGroup']] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)

ProtocolGroup.model_rebuild()