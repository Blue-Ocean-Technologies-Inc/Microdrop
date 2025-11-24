from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Optional


class ZStageConfigData(BaseModel):
    # This configuration ensures that if "param3" is passed, an error is raised
    model_config = ConfigDict(extra='forbid')

    # set default=None to make them truly optional
    zstage_down_position: Optional[float] = Field(default=None, ge=0.0)
    zstage_up_position: Optional[float] = Field(default=None, ge=0.0)

    @model_validator(mode='after')
    def check_up_larger_than_down(self):
        # We can only perform the comparison if BOTH values are provided
        if self.zstage_up_position is not None and self.zstage_down_position is not None:
            if self.zstage_up_position <= self.zstage_down_position:
                raise ValueError('zstage_up_position must be strictly larger than zstage_down_position')

        return self