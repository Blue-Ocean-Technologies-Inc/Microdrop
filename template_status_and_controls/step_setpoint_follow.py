# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""StepSetpointFollowMixin — a status pane follows the selected step's
setpoints.

Mix into a BaseMessageHandler subclass whose listener subscribes to
PROTOCOL_TREE_ROW_SELECTED (its last topic segment, "row_selected", routes
to ``_on_row_selected_triggered``) and declare which model traits follow
which protocol columns::

    class MyStatusMessageHandler(StepSetpointFollowMixin, BaseMessageHandler):
        step_setpoint_columns = Dict(
            Str, Str, value={"voltage": VOLTAGE_COLUMN_ID}
        )

Selecting a step copies those cells into the model, and the pane's
controller observers publish them to the hardware, so the step's setpoints
are live before the user tweaks them in the pane. While a setpoint is being
written the model's ``following_step`` flag is True, so a controller can
tell a follow from a user edit. Skip rules:

- a group or empty selection, or any selection while a protocol runs (the
  executor applies the running step's setpoints itself), follows nothing
  and forgets what was last followed, so the next step selection follows;
- selecting a different step forgets what was followed for the previous
  one, so it follows afresh — also after an intermediate step that had
  nothing to follow;
- a missing cell leaves its setpoint alone; a value the model's trait
  rejects is logged and skipped;
- a rebroadcast of the same step carrying the same cell value as last
  followed for that setpoint is an echo (the tree rebroadcasts on every
  cell edit of the current step) and is skipped, so a pane override
  survives edits to the step's other cells. A changed cell value follows
  again;
- a value equal to the model's current one is not re-set, so nothing is
  re-published.
"""

# Enthought library imports.
from traits.api import Any, Dict, HasTraits, Str, TraitError

# Microdrop package imports.
from pluggable_protocol_tree.models.cell_sync import ProtocolTreeRowSelectedMessage

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class StepSetpointFollowMixin(HasTraits):
    """Follows the selected protocol step's setpoint cells into the model."""

    #: Model trait name → protocol column id (or compound field id) whose
    #: cell that trait follows.
    step_setpoint_columns = Dict(Str, Str)

    #: The step whose setpoints were last followed.
    _last_followed_step_id = Str()

    #: Model trait name → the cell value last followed for
    #: ``_last_followed_step_id`` — what an echo of our own follow looks like.
    _last_followed_setpoints = Dict(Str, Any)

    def _on_row_selected_triggered(self, body):
        """Follow the selected step's setpoints, per the module's skip rules."""

        try:
            msg = ProtocolTreeRowSelectedMessage.deserialize(str(body))
        except Exception as error:
            logger.warning(f"Unparseable row-selected payload: {error}")

            return

        if not msg.step_id or self.model.protocol_running:
            self._last_followed_step_id = ""
            self._last_followed_setpoints = {}

            return

        if msg.step_id != self._last_followed_step_id:
            self._last_followed_step_id = msg.step_id
            self._last_followed_setpoints = {}

        for trait_name, value in self._step_setpoints(msg.cells).items():
            self._follow_step_setpoint(msg.step_id, trait_name, value)

    def _step_setpoints(self, cells):
        """Return ``{model trait name: raw cell value}`` to follow for a step.

        The default reads each ``step_setpoint_columns`` cell. Override when
        a step's setpoints need a gate — e.g. a column whose checkbox decides
        whether the step touches the device at all — and return ``{}`` for a
        step that should leave the pane alone.
        """

        return {
            trait_name: cells.get(col_id)
            for trait_name, col_id in self.step_setpoint_columns.items()
        }

    def _follow_step_setpoint(self, step_id, trait_name, value):
        """Set the model's `trait_name` to the step's `value` unless it is
        missing, an echo of the last follow, unchanged, or rejected."""

        if value is None:
            return

        if self._last_followed_setpoints.get(trait_name) == value:
            return  # echo of our own follow

        # Setpoints are Int end-to-end; a Float cell (a temperature) rounds.
        try:
            setpoint = round(value)

            if setpoint != getattr(self.model, trait_name):
                self.model.following_step = True

                try:
                    setattr(self.model, trait_name, setpoint)
                finally:
                    self.model.following_step = False

        except (TraitError, ValueError, TypeError) as error:
            logger.warning(
                f"Step {step_id}: not applying {trait_name} {value!r}: {error}"
            )

            return

        self._last_followed_setpoints[trait_name] = value
