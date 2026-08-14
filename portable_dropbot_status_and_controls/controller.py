from traits.api import observe

from logger.logger_service import get_logger
from microdrop_utils.decorators import debounce
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from portable_dropbot_controller.consts import (
    CONNECT_TO_PORT, DISCONNECT, MOVE_TRAY, REFRESH_PORTS,
    SET_FLUORESCENCE_LED_RAW, SET_FREQUENCY, SET_ILLUMINATION_RAW,
    SET_LIGHT_INTENSITY, SET_LIGHT_ON, SET_RGB_LIGHT, SET_VOLTAGE,
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

    @observe("model:connect_toggle")
    def _on_connect_toggle_changed(self, event):
        # The model mirrors the actual connection state into the
        # toggle, so only a value CONTRADICTING reality is a click.
        if bool(event.new) == self.model.connected:
            return
        if event.new:
            port_name = self.model.selected_port.strip()
            if port_name:
                publish_message(topic=CONNECT_TO_PORT,
                                message=port_name)
                logger.info(f"Requested Portable Dropbot connect on "
                            f"{port_name}")
        else:
            publish_message(topic=DISCONNECT, message="")
            logger.info("Requested Portable Dropbot disconnect")
        # Snap back to the real state; the backend's
        # connected/disconnected signal is what flips the toggle.
        self.model.connect_toggle = self.model.connected

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

    # Lighting is not actuation, so none of it queues behind realtime
    # mode — every change publishes straight to the hardware.
    @observe("model:light_intensity")
    def _on_light_intensity_changed(self, event):
        publish_message(topic=SET_LIGHT_INTENSITY,
                        message=str(int(event.new)))
        logger.debug(f"Light intensity --> {event.new} %")

    @observe("model:light_on")
    def _on_light_on_changed(self, event):
        publish_message(topic=SET_LIGHT_ON, message=str(bool(event.new)))
        logger.debug(f"Light --> {'on' if event.new else 'off'}")

    @observe("model:rgb_light")
    def _on_rgb_light_changed(self, event):
        publish_message(topic=SET_RGB_LIGHT, message=str(event.new))
        logger.debug(f"RGB light --> {event.new}")

    @debounce(wait_seconds=0.3)
    def illumination_raw_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    @observe("model:illumination_raw")
    def _on_illumination_raw_changed(self, event):
        publish_message(topic=SET_ILLUMINATION_RAW,
                        message=str(int(event.new)))
        logger.debug(f"Illumination raw --> {event.new}")

    @debounce(wait_seconds=0.3)
    def fluorescence_led_raw_setattr(self, info, obj, traitname,
                                     value):
        return super().setattr(info, obj, traitname, value)

    @observe("model:fluorescence_led_raw")
    def _on_fluorescence_led_raw_changed(self, event):
        publish_message(topic=SET_FLUORESCENCE_LED_RAW,
                        message=str(int(event.new)))
        logger.debug(f"Fluorescence LED raw --> {event.new}")

    @observe("model:fluorescence_led_default_button")
    def _on_fluorescence_led_default(self, event):
        # The vendor tab's "Default (0)": zero the spinner and send it
        # regardless (the trait observer stays quiet when already 0).
        self.model.fluorescence_led_raw = 0
        publish_message(topic=SET_FLUORESCENCE_LED_RAW, message="0")
