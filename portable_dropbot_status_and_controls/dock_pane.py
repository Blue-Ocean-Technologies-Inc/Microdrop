from microdrop_style.icons.icons import ICON_DROP_EC
from template_status_and_controls.base_dock_pane import BaseStatusDockPane
from template_status_and_controls.realtime_mode_icon_mixin import (
    RealtimeModeIconMixin,
)

from .calibration_controller import CalibrationController
from .calibration_message_handler import (
    PortableDropbotCalibrationMessageHandler,
)
from .calibration_model import PortableDropbotCalibrationModel
from .calibration_view import CalibrationView
from .consts import (
    CALIBRATION_LISTENER, MOTOR_PARAMS_LISTENER, MOTORS_LISTENER,
    PKG, PKG_name, PMT_LISTENER, POWER_SYSTEM_LISTENER,
    TEMP_LIGHTING_LISTENER,
)
from .controller import ControlsController
from .message_handler import PortableDropbotStatusAndControlsMessageHandler
from .model import PortableDropbotStatusAndControlsModel
from .motor_params_controller import MotorParamsController
from .motor_params_message_handler import (
    PortableDropbotMotorParamsMessageHandler,
)
from .motor_params_model import PortableDropbotMotorParamsModel
from .motor_params_view import MotorParamsView
from .motors_controller import MotorsController
from .motors_message_handler import PortableDropbotMotorsMessageHandler
from .motors_model import PortableDropbotMotorsModel
from .motors_view import MotorsView
from .pmt_controller import PmtController
from .pmt_message_handler import PortableDropbotPmtMessageHandler
from .pmt_model import PortableDropbotPmtModel
from .pmt_view import PmtView
from .power_system_controller import PowerSystemController
from .power_system_message_handler import (
    PortableDropbotPowerSystemMessageHandler,
)
from .power_system_model import PortableDropbotPowerSystemModel
from .power_system_view import PowerSystemView
from .temp_lighting_controller import TempLightingController
from .temp_lighting_message_handler import (
    PortableDropbotTempLightingMessageHandler,
)
from .temp_lighting_model import PortableDropbotTempLightingModel
from .temp_lighting_view import TempLightingView
from .view import UnifiedView


class PortableDropbotStatusAndControls(RealtimeModeIconMixin,
                                       BaseStatusDockPane):
    """Dock pane for Portable Dropbot status display and controls."""

    id = PKG + ".dock_pane"
    name = PKG_name

    view = UnifiedView
    status_bar_icon_glyph = ICON_DROP_EC

    def _create_model(self):
        return PortableDropbotStatusAndControlsModel()

    def _create_controller(self):
        return ControlsController(self.model)

    def _create_message_handler(self):
        return PortableDropbotStatusAndControlsMessageHandler(
            model=self.model,
            name=f"{PKG}_listener",
        )


class PortableDropbotSecondaryDockPane(BaseStatusDockPane):
    """Base for every Portable Dropbot pane beyond the status one:
    the portable is one instrument with one connection, and the
    status pane's icon already shows it, so none of these contribute
    a status-bar icon of their own."""

    def _populate_status_bar(self, event=None):
        """Undecorated on purpose — dropping the base observer is how
        a pane opts out (see the base docstring)."""


class PortableDropbotMotorsDockPane(PortableDropbotSecondaryDockPane):
    """Dock pane for the Portable Dropbot motor panel: mechanism
    macros plus the advanced per-motor moves."""

    id = PKG + ".motors_dock_pane"
    name = "Portable Dropbot Motors"

    view = MotorsView

    def _create_model(self):
        return PortableDropbotMotorsModel()

    def _create_controller(self):
        return MotorsController(self.model)

    def _create_message_handler(self):
        return PortableDropbotMotorsMessageHandler(
            model=self.model,
            name=MOTORS_LISTENER,
        )


class PortableDropbotCalibrationDockPane(PortableDropbotSecondaryDockPane):
    """Dock pane for capacitance calibration: the validated ML macro
    plus the ML-path / gain / cal-caps provisioning."""

    id = PKG + ".calibration_dock_pane"
    name = "Portable Dropbot Calibration"

    view = CalibrationView

    def _create_model(self):
        return PortableDropbotCalibrationModel()

    def _create_controller(self):
        return CalibrationController(self.model)

    def _create_message_handler(self):
        return PortableDropbotCalibrationMessageHandler(
            model=self.model,
            name=CALIBRATION_LISTENER,
        )


class PortableDropbotTempLightingDockPane(PortableDropbotSecondaryDockPane):
    """Dock pane for per-channel heater control (with PID tuning) and
    the vendor's raw lighting controls."""

    id = PKG + ".temp_lighting_dock_pane"
    name = "Portable Dropbot Temp & Lighting"

    view = TempLightingView

    def _create_model(self):
        return PortableDropbotTempLightingModel()

    def _create_controller(self):
        return TempLightingController(self.model)

    def _create_message_handler(self):
        return PortableDropbotTempLightingMessageHandler(
            model=self.model,
            name=TEMP_LIGHTING_LISTENER,
        )


class PortableDropbotPmtDockPane(PortableDropbotSecondaryDockPane):
    """Dock pane for the PMT: power, gain, and the acquire macro."""

    id = PKG + ".pmt_dock_pane"
    name = "Portable Dropbot PMT"

    view = PmtView

    def _create_model(self):
        return PortableDropbotPmtModel()

    def _create_controller(self):
        return PmtController(self.model)

    def _create_message_handler(self):
        return PortableDropbotPmtMessageHandler(
            model=self.model,
            name=PMT_LISTENER,
        )


class PortableDropbotPowerSystemDockPane(PortableDropbotSecondaryDockPane):
    """Dock pane for fan and buzzer control; unlocked only in
    Advanced Mode."""

    id = PKG + ".power_system_dock_pane"
    name = "Portable Dropbot Power System"

    view = PowerSystemView

    def _create_model(self):
        return PortableDropbotPowerSystemModel()

    def _create_controller(self):
        return PowerSystemController(self.model)

    def _create_message_handler(self):
        return PortableDropbotPowerSystemMessageHandler(
            model=self.model,
            name=POWER_SYSTEM_LISTENER,
        )


class PortableDropbotMotorParamsDockPane(PortableDropbotSecondaryDockPane):
    """Dock pane for per-motor mechanical param tuning (read / RAM
    write / flash preset / reboot); unlocked only in Advanced Mode."""

    id = PKG + ".motor_params_dock_pane"
    name = "Portable Dropbot Motor Params"

    view = MotorParamsView

    def _create_model(self):
        return PortableDropbotMotorParamsModel()

    def _create_controller(self):
        return MotorParamsController(self.model)

    def _create_message_handler(self):
        return PortableDropbotMotorParamsMessageHandler(
            model=self.model,
            name=MOTOR_PARAMS_LISTENER,
        )
