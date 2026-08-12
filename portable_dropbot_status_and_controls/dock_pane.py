from microdrop_style.icons.icons import ICON_DROP_EC
from template_status_and_controls.base_dock_pane import BaseStatusDockPane
from template_status_and_controls.realtime_mode_icon_mixin import (
    RealtimeModeIconMixin,
)

from .consts import MOTORS_LISTENER, PKG, PKG_name
from .controller import ControlsController
from .message_handler import PortableDropbotStatusAndControlsMessageHandler
from .model import PortableDropbotStatusAndControlsModel
from .motors_controller import MotorsController
from .motors_message_handler import PortableDropbotMotorsMessageHandler
from .motors_model import PortableDropbotMotorsModel
from .motors_view import MotorsView
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


class PortableDropbotMotorsDockPane(BaseStatusDockPane):
    """Dock pane for the Portable Dropbot motor panel: mechanism
    macros plus the advanced per-motor moves."""

    id = PKG + ".motors_dock_pane"
    name = f"{PKG_name} Motors"

    view = MotorsView

    def _populate_status_bar(self, event=None):
        """No status-bar icon of its own: the portable is one
        instrument with one connection, and the status pane's icon
        already shows it. Undecorated on purpose — dropping the base
        observer is how a pane opts out (see the base docstring)."""

    def _create_model(self):
        return PortableDropbotMotorsModel()

    def _create_controller(self):
        return MotorsController(self.model)

    def _create_message_handler(self):
        return PortableDropbotMotorsMessageHandler(
            model=self.model,
            name=MOTORS_LISTENER,
        )
