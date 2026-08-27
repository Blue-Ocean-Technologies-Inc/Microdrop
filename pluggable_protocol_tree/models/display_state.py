# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Slim payload for `PROTOCOL_TREE_DISPLAY_STATE` — what the
pluggable tree pushes to the device viewer when the user
selects/deselects a step.

Strict subset of `device_viewer.models.messages.DeviceViewerMessageModel`:
only the fields the DV actually needs from us. Channel resolution is
left to the DV (it owns electrode->channel geometry via its own model).
"""

from pydantic import BaseModel


class ProtocolTreeDisplayMessage(BaseModel):
    electrodes: list[str] = []
    routes: list[list[str]] = []
    step_id: str | None = None
    step_label: str | None = None
    free_mode: bool = False
    editable: bool = True
    # The step's route-execution params keyed by the DV sidebar's names
    # (duration / repetitions / repeat_duration / trail_length /
    # trail_overlay / soft_start / soft_terminate / linear_repeats —
    # same contract as StepParamsCommitMessage minus step_id). None in
    # free mode; the DV then disables its commit-to-step button.
    execution_params: dict | None = None

    def serialize(self) -> str:
        return self.model_dump_json()

    @classmethod
    def deserialize(cls, json_str: str) -> "ProtocolTreeDisplayMessage":
        return cls.model_validate_json(json_str)
