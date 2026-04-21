from pydantic import BaseModel


class StepParamsCommitMessage(BaseModel):
    step_id: str
    duration: float
    repetitions: int
    repeat_duration: int
    trail_length: int
    trail_overlay: int
    soft_start: bool
    soft_terminate: bool
    linear_repeats: bool

    def serialize(self) -> str:
        return self.model_dump_json()

    @classmethod
    def deserialize(cls, json_str: str) -> "StepParamsCommitMessage":
        return cls.model_validate_json(json_str)
