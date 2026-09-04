# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import math

# Third-party imports.
import pint

# Enthought library imports.
from apptools.preferences.api import get_default_preferences
from traits.api import Bool, Enum, Instance, Str, observe

# Microdrop package imports.
from dropbot_preferences_ui.consts import (
    UI_DEFAULT_FREQUENCY,
    UI_DEFAULT_FREQUENCY_KEY,
    UI_DEFAULT_MAX_FREQUENCY,
    UI_DEFAULT_MAX_VOLTAGE,
    UI_DEFAULT_MIN_FREQUENCY,
    UI_DEFAULT_MIN_VOLTAGE,
    UI_DEFAULT_VOLTAGE,
    UI_DEFAULT_VOLTAGE_KEY,
    UI_MAX_FREQUENCY_KEY,
    UI_MAX_VOLTAGE_KEY,
    UI_MIN_FREQUENCY_KEY,
    UI_MIN_VOLTAGE_KEY,
    VOLTAGE_FREQUENCY_RANGE_PREFERENCES_PATH,
)
from microdrop_application.helpers import get_microdrop_redis_globals_manager
from template_status_and_controls.base_model import BaseStatusModel

# Microdrop utils imports.
from microdrop_utils.force_math_helpers import force_for_step
from microdrop_utils.traitsui_qt_helpers import RangeWithSteppedSpinViewHint
from microdrop_utils.ureg_helpers import ureg

# Local imports.
from .consts import (
    DIELECTRIC_MATERIALS,
    DROPBOT_CHIP_INSERTED_IMAGE,
    DROPBOT_IMAGE,
    connected_color,
    connected_no_device_color,
    disconnected_color,
    halted_color,
)
from .preferences import DropbotStatusAndControlsPreferences

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)
app_globals = get_microdrop_redis_globals_manager()

N_DISPLAY_DIGITS = 3


class DropbotStatusAndControlsModel(BaseStatusModel):
    """Model for DropBot status display and controls.

    Extends BaseStatusModel with DropBot-specific controls and sensor readings.
    Connection/mode/icon traits and their observers are inherited.
    """

    # ---- Class-level constants ----------------------------------------
    DEFAULT_ICON_PATH = DROPBOT_IMAGE
    CHIP_INSERTED_ICON_PATH = DROPBOT_CHIP_INSERTED_IMAGE
    DISCONNECTED_COLOR = disconnected_color
    CONNECTED_NO_DEVICE_COLOR = connected_no_device_color
    CONNECTED_COLOR = connected_color
    HALTED_COLOR = halted_color

    # ---- Hardware controls (user-writable via UI) ----------------------
    # Min/max/default read from app_globals, where dropbot_preferences_ui's
    # VoltageFrequencyRangePreferences publishes them (owner-publishes
    # pattern, #610) — falls back to its consts if nothing has published
    # yet (e.g. this plugin's app loads before dropbot_preferences_ui's).
    voltage = RangeWithSteppedSpinViewHint(
        int(app_globals.get(UI_MIN_VOLTAGE_KEY, UI_DEFAULT_MIN_VOLTAGE)),
        int(app_globals.get(UI_MAX_VOLTAGE_KEY, UI_DEFAULT_MAX_VOLTAGE)),
        value=int(app_globals.get(UI_DEFAULT_VOLTAGE_KEY, UI_DEFAULT_VOLTAGE)),
        suffix=" V",
        desc="Voltage to set on the DropBot device (V)",
    )
    frequency = RangeWithSteppedSpinViewHint(
        int(app_globals.get(UI_MIN_FREQUENCY_KEY, UI_DEFAULT_MIN_FREQUENCY)),
        int(app_globals.get(UI_MAX_FREQUENCY_KEY, UI_DEFAULT_MAX_FREQUENCY)),
        value=int(app_globals.get(UI_DEFAULT_FREQUENCY_KEY, UI_DEFAULT_FREQUENCY)),
        step=100,
        suffix=" Hz",
        desc="Frequency to set on the DropBot device (Hz)",
    )

    # ---- Device-specific status ----------------------------------------
    chip_status_text = Str("Absent")

    # ---- Sensor readings (raw values set by message handler) -----------
    # NaN magnitude means "no reading available"
    capacitance = Instance(pint.Quantity, desc="Raw capacitance (pF)")
    voltage_readback = Instance(pint.Quantity, desc="Voltage readback from device (V)")
    c_device = Instance(pint.Quantity, desc="Capacitance density / c_device (pF/mm²)")
    force = Instance(pint.Quantity, desc="Calculated force (mN/m)")

    # ---- Dielectric ----------------------------------
    dielectric_material = Enum(
        *list(DIELECTRIC_MATERIALS.keys()),
        desc="Dielectric material for thickness calculation",
    )
    dielectric_thickness = Instance(
        pint.Quantity, desc="Calculated dielectric thickness (um)"
    )
    show_dielectric_info = Bool(
        desc="Whether the dielectric readout section is visible"
    )
    # --------------------------------------------------

    preferences = Instance(DropbotStatusAndControlsPreferences)

    def _capacitance_default(self):
        return ureg("nan pF")

    def _voltage_readback_default(self):
        return ureg("nan V")

    def _c_device_default(self):
        return ureg("nan pF/mm^2")

    def _force_default(self):
        return ureg("nan mN/m")

    def _dielectric_thickness_default(self):
        return ureg("nan um")

    def _dielectric_material_default(self):
        return self.preferences.default_dielectric_material

    def _show_dielectric_info_default(self):
        return self.preferences.show_dielectric_info

    # ---- Formatted sensor readings for display -------------------------
    capacitance_display = Str("-")
    voltage_readback_display = Str("-")
    frequency_display = Str("-")
    c_device_display = Str("-")
    force_display = Str("-")
    dielectric_thickness_display = Str("-")

    # ------------------------------------------------------------------ #
    # BaseStatusModel hook                                                 #
    # ------------------------------------------------------------------ #

    def _update_chip_display(self, inserted: bool) -> None:
        self.chip_status_text = "Present" if inserted else "Absent"

    # ------------------------------------------------------------------ #
    # Observers                                                            #
    # ------------------------------------------------------------------ #

    @observe("realtime_mode")
    def _reset_readings_on_realtime_off(self, event):
        """Clear sensor displays when realtime mode is disabled."""
        if not event.new:
            self.reset_traits(
                [
                    "capacitance",
                    "voltage_readback",
                    "force",
                    "dielectric_thickness",
                ]
            )
            self.frequency_display = "-"

    @observe("capacitance")
    def _update_capacitance_display(self, event):
        self.capacitance_display = self._format_reading(event.new)

    @observe("voltage_readback")
    def _update_voltage_readback_display(self, event):
        self.voltage_readback_display = self._format_reading(event.new)

    @observe("frequency,realtime_mode")
    def _update_frequency_display(self, event):
        if self.realtime_mode:
            self.frequency_display = self._format_reading(self.frequency * ureg.Hz)

    @observe("c_device")
    def _update_c_device_display(self, event):
        self.c_device_display = self._format_reading(event.new)

    @observe("force")
    def _update_force_display(self, event):
        self.force_display = self._format_reading(event.new)

    @observe("dielectric_thickness")
    def _update_dielectric_thickness_display(self, event):
        self.dielectric_thickness_display = self._format_reading(event.new)

    @observe("voltage_readback, c_device")
    def _recalculate_force(self, event):
        """Recalculate force when voltage_readback or c_device changes."""
        if math.isnan(self.voltage_readback.magnitude) or math.isnan(
            self.c_device.magnitude
        ):
            self.force = ureg("nan mN/m")
            return
        force = force_for_step(self.voltage_readback.magnitude, self.c_device.magnitude)
        self.force = (
            ureg(f"{force:.4f} mN/m") if force is not None else ureg("nan mN/m")
        )

    @observe("dielectric_material, c_device")
    def _recalculate_dielectric_thickness(self, event):
        """Recalculate dielectric thickness: d = epsilon_r * epsilon_0 / C_device.

        Triggered automatically when ``dielectric_material`` or ``c_device``
        changes.  Uses pint's built-in ``vacuum_permittivity`` for epsilon_0
        and converts the result to micrometres.
        """
        if not self.dielectric_material:
            self.reset_traits("dielectric_thickness")
            return

        epsilon_r = DIELECTRIC_MATERIALS.get(self.dielectric_material)
        if epsilon_r is None:
            self.reset_traits("dielectric_thickness")
            return

        if self.c_device is None or self.c_device.magnitude <= 0:
            self.reset_traits("dielectric_thickness")
            return

        # d = epsilon_r * epsilon_0 / C_device
        # Convert to micrometres

        self.dielectric_thickness = (
            epsilon_r * ureg.vacuum_permittivity / self.c_device
        ).to("um")
        logger.info(
            f"Dielectric thickness calculated: {self.dielectric_thickness:.3f} um "
            f"(material={self.dielectric_material}, "
            f"epsilon_r={epsilon_r}, c_device={self.c_device} pF/mm^2)"
        )

    @observe("dielectric_material")
    def _update_preferred_dielectric(self, event):
        self.preferences.default_dielectric_material = event.new

    @observe("show_dielectric_info")
    def _persist_show_dielectric_info(self, event):
        if self.preferences.show_dielectric_info != event.new:
            self.preferences.show_dielectric_info = event.new

    @observe("preferences:show_dielectric_info")
    def _sync_show_dielectric_info_from_preferences(self, event):
        if self.show_dielectric_info != event.new:
            self.show_dielectric_info = event.new

    @observe("voltage, frequency")
    def _update_prefs(self, event):
        """Persist the last-applied voltage/frequency across restarts.

        Writes straight to the ETS preferences node dropbot_preferences_ui's
        VoltageFrequencyRangePreferences persists under (#610), by path,
        rather than importing that plugin's preferences model. Envisage
        installs the application's preferences node as apptools' default
        (envisage.application.Application.__init__), so this lands in the
        exact node PreferencesHelper subclasses read from/write to; if a
        VoltageFrequencyRangePreferences instance is alive it picks up the
        change via its preferences listener and mirrors it to app_globals
        itself — this is the only writer of ui_default_voltage/frequency.
        """
        logger.debug(f"Updating preferences: {event}")
        get_default_preferences().set(
            f"{VOLTAGE_FREQUENCY_RANGE_PREFERENCES_PATH}.ui_default_{event.name}",
            event.new,
        )

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _format_reading(value):
        if value is None or math.isnan(value.magnitude):
            return "-"
        return f"{value.to_compact():.{N_DISPLAY_DIGITS}g~H}"
