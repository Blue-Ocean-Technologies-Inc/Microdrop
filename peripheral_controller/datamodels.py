from pydantic import BaseModel, ConfigDict, Field, model_validator


class ZStageConfigData(BaseModel):
    # This configuration ensures that if "param3" is passed, an error is raised
    model_config = ConfigDict(extra='forbid')

    zstage_down_position: float = Field(ge=0.0)
    zstage_up_position: float = Field(ge=0.0)

    @model_validator(mode='after')
    def check_up_larger_than_down(self):
        if self.zstage_up_position <= self.zstage_down_position:
            raise ValueError('zstage_up_position must be strictly larger than zstage_down_position')
        return self