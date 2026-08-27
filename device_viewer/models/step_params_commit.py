# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Wire schema for ``STEP_PARAMS_COMMIT`` — the device viewer sidebar's
route-executor params pushed to the selected protocol step.

Canonical home (the device viewer owns/publishes the topic). The legacy
``protocol_grid.models.step_params_commit`` copy stays untouched until
PPT-9 deletes protocol_grid; both serialize to the same JSON.

Key mapping on the pluggable_protocol_tree side: ``repetitions`` is the
tree's ``route_repetitions`` column and ``soft_terminate`` is ``soft_end``;
the remaining keys match their column ids directly.
"""

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
