from traits.api import observe, Instance
from traitsui.api import Controller

from dropbot_controller.consts import SET_VOLTAGE, SET_FREQUENCY, SET_REALTIME_MODE
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.decorators import debounce

from template_status_and_controls.base_controller import BaseStatusController

from logger.logger_service import get_logger

logger = get_logger(__name__)


class MockDropbotController(BaseStatusController):
    """Controller for the MockDropBot dock pane."""

    mock_controller = Instance("mock_dropbot_controller.mock_controller.MockDropbotController")

    @debounce(wait_seconds=0.3)
    def base_capacitance_pf_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    @debounce(wait_seconds=0.3)
    def capacitance_delta_pf_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    @debounce(wait_seconds=0.3)
    def capacitance_noise_pf_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    @debounce(wait_seconds=0.3)
    def stream_interval_ms_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    @observe("model:base_capacitance_pf")
    def _on_base_cap_changed(self, event):
        if self.mock_controller:
            self.mock_controller.base_capacitance_pf = event.new

    @observe("model:capacitance_delta_pf")
    def _on_delta_cap_changed(self, event):
        if self.mock_controller:
            self.mock_controller.capacitance_delta_pf = event.new

    @observe("model:capacitance_noise_pf")
    def _on_noise_cap_changed(self, event):
        if self.mock_controller:
            self.mock_controller.capacitance_noise_pf = event.new

    @observe("model:stream_interval_ms")
    def _on_interval_changed(self, event):
        if self.mock_controller:
            self.mock_controller.stream_interval_ms = event.new
            self.mock_controller.restart_stream()
