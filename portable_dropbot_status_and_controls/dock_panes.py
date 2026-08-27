# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from microdrop_style.icons.icons import ICON_DROP_EC
from template_status_and_controls.base_dock_pane import BaseStatusDockPane
from template_status_and_controls.realtime_mode_icon_mixin import (
    RealtimeModeIconMixin,
)

from .consts import (
    ADVANCED_CONTROLS_LISTENER, CALIBRATION_LISTENER,
    MORE_CONTROLS_LISTENER, MOTORS_LISTENER, PKG, PKG_name,
)
from .controllers.advanced_controls_controller import (
    AdvancedControlsController,
)
from .controllers.calibration_controller import CalibrationController
from .controllers.more_controls_controller import MoreControlsController
from .controllers.motors_controller import MotorsController
from .controllers.status_controls_pane_controller import (
    PortableDropbotStatusAndControlsController,
)
from .message_handlers.advanced_controls_message_handler import (
    PortableDropbotAdvancedControlsMessageHandler,
)
from .message_handlers.calibration_message_handler import (
    PortableDropbotCalibrationMessageHandler,
)
from .message_handlers.message_handler import (
    PortableDropbotStatusAndControlsMessageHandler,
)
from .message_handlers.more_controls_message_handler import (
    PortableDropbotMoreControlsMessageHandler,
)
from .message_handlers.motors_message_handler import (
    PortableDropbotMotorsMessageHandler,
)
from .models.advanced_controls_model import (
    PortableDropbotAdvancedControlsModel,
)
from .models.calibration_model import PortableDropbotCalibrationModel
from .models.model import PortableDropbotStatusAndControlsModel
from .models.more_controls_model import PortableDropbotMoreControlsModel
from .models.motors_model import PortableDropbotMotorsModel
from .views.advanced_controls_view import AdvancedControlsView
from .views.calibration_view import CalibrationView
from .views.more_controls_view import MoreControlsView
from .views.motors_view import MotorsView
from .views.view import UnifiedView


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
        return PortableDropbotStatusAndControlsController(self.model)

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


class PortableDropbotMoreControlsDockPane(PortableDropbotSecondaryDockPane):
    """Dock pane for everything beyond the everyday status-pane
    controls, one collapsible group per subsystem: per-channel heater
    control (with PID tuning), the vendor's raw lighting controls,
    and the PMT (power, gain, acquire)."""

    id = PKG + ".more_controls_dock_pane"
    name = "More Portable Dropbot Controls"

    view = MoreControlsView

    def _create_model(self):
        return PortableDropbotMoreControlsModel()

    def _create_controller(self):
        return MoreControlsController(self.model)

    def _create_message_handler(self):
        return PortableDropbotMoreControlsMessageHandler(
            model=self.model,
            name=MORE_CONTROLS_LISTENER,
        )


class PortableDropbotAdvancedControlsDockPane(
        PortableDropbotSecondaryDockPane):
    """Dock pane for the advanced-mode-locked controls: the
    power-system buzzer and per-motor mechanical param tuning (read /
    RAM write / flash preset / reboot)."""

    id = PKG + ".advanced_controls_dock_pane"
    name = "Advanced Portable Dropbot Controls"

    view = AdvancedControlsView

    def _create_model(self):
        return PortableDropbotAdvancedControlsModel()

    def _create_controller(self):
        return AdvancedControlsController(self.model)

    def _create_message_handler(self):
        return PortableDropbotAdvancedControlsMessageHandler(
            model=self.model,
            name=ADVANCED_CONTROLS_LISTENER,
        )
