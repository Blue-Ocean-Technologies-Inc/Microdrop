# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Stand-ins for column handlers that contribute their own pre-flight
checks through the ``BaseColumnHandler.preflight_checks`` hook (default:
no checks).

Every hardware check lives here, in the column that drives the hardware:
the voltage/frequency column (standing in for ``dropbot_protocol_controls``)
checks the DropBot, its HV supply, the chip and the step voltages; video,
heater and magnet check their own boards. Each reads its hardware from the
rig (the real ones from their plugin's app_globals keys); the snapshot
carries only protocol facts. In preview, nothing is driven, so every
hardware check is skipped.
"""

# Enthought library imports.
from traits.api import Any, Bool, HasTraits, Str

# Microdrop package imports.
from pluggable_protocol_tree.preflight.checks import ColumnCheck, Result, step_name

#: Why a hardware check is skipped in preview.
PREVIEW_TOOLTIP = "Preview drives no hardware."

#: Why a check is skipped without a DropBot.
NEEDS_DROPBOT_TOOLTIP = "Needs a connected DropBot."


class MockColumnHandler(HasTraits):
    """The slice of ``BaseColumnHandler`` the hook needs."""

    #: The column's id, as RowManager knows it.
    column_id = Str

    #: The column's display name.
    name = Str

    #: Whether the column has protocol start/end hooks, so an unused one is
    #: worth a warning (``has_protocol_level_hooks``).
    has_protocol_hooks = Bool(True)

    #: The harness rig the column reads its hardware from.
    rig = Any

    def preflight_checks(self, context):
        """The column's own checks for a run over ``context``: none."""
        return []

    def is_used(self, context):
        """Whether any step of the run has a value in this column."""
        return any(step.get(self.column_id) for step in context.run_steps())

    def check(self, suffix, label, result, category="Peripherals"):
        """A ``ColumnCheck`` with id ``<column id>:<suffix>``."""
        return ColumnCheck(
            id=f"{self.column_id}:{suffix}",
            label=label,
            result=result,
            category=category,
        )


class VoltageFrequencyColumnHandler(MockColumnHandler):
    """Stands in for ``dropbot_protocol_controls``' voltage and frequency
    columns: the DropBot, its HV supply, the chip, and step limits."""

    def preflight_checks(self, context):
        if context.preview_mode:
            skipped = Result(status="skip", tooltip=PREVIEW_TOOLTIP)
            results = dict.fromkeys(("dropbot", "hv_supply", "chip", "limits"), skipped)

        else:
            results = self._hardware_results(context)

        return [
            self.check("dropbot", "DropBot", results["dropbot"], "Hardware"),
            self.check("hv_supply", "HV supply", results["hv_supply"], "Hardware"),
            self.check("chip", "Chip", results["chip"], "Hardware"),
            self.check("limits", "Voltage", results["limits"], "Hardware"),
        ]

    def _hardware_results(self, context):
        rig = self.rig

        if not rig.dropbot_connected:
            skipped = Result(status="skip", tooltip=NEEDS_DROPBOT_TOOLTIP)

            return {
                "dropbot": Result(
                    status="fail",
                    detail="Not found",
                    tooltip="No DropBot answered on USB.",
                    problem="DropBot disconnected",
                ),
                "hv_supply": skipped,
                "chip": skipped,
                "limits": skipped,
            }

        return {
            "dropbot": Result(status="pass"),
            "hv_supply": self._hv_result(),
            "chip": self._chip_result(),
            "limits": self._limits_result(context),
        }

    def _hv_result(self):
        if self.rig.hv_powered:
            return Result(status="pass")

        return Result(
            status="fail",
            detail="No 12 V",
            tooltip="The HV supply reports no power.",
            problem="HV unpowered",
        )

    def _chip_result(self):
        if self.rig.chip_inserted:
            return Result(status="pass")

        return Result(
            status="fail",
            detail="Socket empty",
            tooltip="No chip in the socket.",
            problem="Chip missing",
        )

    def _limits_result(self, context):
        rig = self.rig

        for step in context.run_steps():
            if (
                step["voltage"] > rig.max_voltage
                or step["frequency"] > rig.max_frequency
            ):
                name = step_name(step)
                tooltip = (
                    f"{name}: {step['voltage']} V / {step['frequency']} Hz exceeds "
                    f"the DropBot's {rig.max_voltage} V / {rig.max_frequency} Hz"
                )

                return Result(
                    status="fail",
                    detail=name,
                    tooltip=tooltip,
                    problem="Voltage too high",
                )

        return Result(status="pass")


class VideoColumnHandler(MockColumnHandler):
    """Capture steps need a camera."""

    def preflight_checks(self, context):
        if not self.is_used(context):
            return []

        if context.preview_mode:
            skipped = Result(status="skip", tooltip=PREVIEW_TOOLTIP)

            return [self.check("camera", "Camera", skipped)]

        if self.rig.camera_present:
            return [self.check("camera", "Camera", Result(status="pass"))]

        capturing = sum(1 for step in context.run_steps() if step.get("video"))
        tooltip = f"{capturing} steps capture images, but no camera was found."
        result = Result(
            status="warn",
            detail=f"{capturing} capture steps",
            tooltip=tooltip,
            problem="Camera missing",
        )

        return [self.check("camera", "Camera", result)]


class BoardColumnHandler(MockColumnHandler):
    """A column driving a peripheral board, which must be connected."""

    #: The rig trait saying whether the board answers.
    connected_trait = Str

    def preflight_checks(self, context):
        if not self.is_used(context):
            return []

        if context.preview_mode:
            result = Result(status="skip", tooltip=PREVIEW_TOOLTIP)

        elif getattr(self.rig, self.connected_trait):
            result = Result(status="pass")

        else:
            tooltip = (
                f"The {self.name} column is used, but no {self.name.lower()} "
                f"board is connected."
            )
            result = Result(
                status="fail",
                detail="Column used",
                tooltip=tooltip,
                problem=f"{self.name} disconnected",
            )

        return [self.check("connected", self.name, result)]


def make_column_handlers(rig):
    """The protocol's columns, in column order, reading ``rig``."""
    return [
        # Every step has a voltage, so the column is never unused.
        VoltageFrequencyColumnHandler(
            column_id="voltage", name="Voltage", has_protocol_hooks=False, rig=rig
        ),
        VideoColumnHandler(column_id="video", name="Video", rig=rig),
        BoardColumnHandler(
            column_id="heater",
            name="Heater",
            connected_trait="heater_connected",
            rig=rig,
        ),
        BoardColumnHandler(
            column_id="magnet",
            name="Magnet",
            connected_trait="magnet_connected",
            rig=rig,
        ),
    ]
