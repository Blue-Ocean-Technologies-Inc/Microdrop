from traits.api import observe

from logger.logger_service import get_logger
from microdrop_utils.decorators import debounce
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from portable_dropbot_controller.consts import (
    CONNECT_TO_PORT, MOVE_TRAY, REFRESH_PORTS, SET_FREQUENCY,
    SET_LIGHT_INTENSITY, SET_VOLTAGE,
)
from template_status_and_controls.base_controller import (
    BaseStatusController,
)

logger = get_logger(__name__)


class ControlsController(BaseStatusController):
    """Portable Dropbot controls controller: voltage and frequency
    edits publish to the portable backend (queued while realtime mode
    is off, exactly as the DropBot pane does)."""

    def init(self, info):
        # Populate the port picker as soon as the pane opens; the
        # backend answers on PORTS_UPDATED.
        publish_message(topic=REFRESH_PORTS, message="")
        return super().init(info)

    @observe("model:refresh_ports_button")
    def _on_refresh_ports(self, event):
        publish_message(topic=REFRESH_PORTS, message="")

    @observe("model:connect_button")
    def _on_connect_to_port(self, event):
        # Straight publish, never queued: connecting is exactly what
        # must work while the device is offline.
        port_name = self.model.selected_port.strip()
        if port_name:
            publish_message(topic=CONNECT_TO_PORT, message=port_name)
            logger.info(f"Requested Portable Dropbot connect on "
                        f"{port_name}")

    @observe("model:tray_toggle_clicked")
    def _on_tray_toggle_clicked(self, event):
        # The device picture is the tray button: the backend reads the
        # current tray position and moves it the other way.
        if self.model.connected:
            publish_message(topic=MOVE_TRAY, message="toggle")
            logger.info("Device picture clicked: toggling tray")

    @debounce(wait_seconds=0.3)
    def voltage_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    @debounce(wait_seconds=0.3)
    def frequency_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    @observe("model:voltage")
    def _on_voltage_changed(self, event):
        if self._publish_or_queue(topic=SET_VOLTAGE,
                                  message=str(int(event.new))):
            logger.debug(f"Voltage --> {event.new} V")

    @observe("model:frequency")
    def _on_frequency_changed(self, event):
        if self._publish_or_queue(topic=SET_FREQUENCY,
                                  message=str(int(event.new))):
            logger.debug(f"Frequency --> {event.new} Hz")

    @debounce(wait_seconds=0.3)
    def light_intensity_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    @observe("model:light_intensity")
    def _on_light_intensity_changed(self, event):
        if self._publish_or_queue(topic=SET_LIGHT_INTENSITY,
                                  message=str(int(event.new))):
            logger.debug(f"Light intensity --> {event.new} %")
