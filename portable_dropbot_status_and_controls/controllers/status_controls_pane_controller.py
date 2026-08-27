import json

from traits.api import observe

from logger.logger_service import get_logger
from microdrop_utils.decorators import debounce
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from portable_dropbot_controller.consts import (
    CONNECT_TO_PORT, DISCONNECT, LOCK_CHIP, MOVE_MAGNET, MOVE_TRAY,
    REFRESH_PORTS, SET_FAN, SET_FREQUENCY, SET_LIGHT_INTENSITY,
    SET_LIGHT_ON, SET_RGB_LIGHT, SET_VOLTAGE,
)
from template_status_and_controls.base_controller import (
    BaseStatusController,
)

logger = get_logger(__name__)


class PortableDropbotStatusAndControlsController(BaseStatusController):
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

    @observe("model:icon_color")
    def _sync_rgb_led_to_status(self, event):
        # The box's RGB indicator LED mirrors the status icon: yellow
        # while connected without a chip, green with one, red on a
        # halt. Nothing to send while disconnected (the link is gone,
        # and the board's own power-down handles its LED).
        if not self.model.connected:
            return
        color = {
            self.model.CONNECTED_COLOR: "green",
            self.model.CONNECTED_NO_DEVICE_COLOR: "yellow",
            self.model.HALTED_COLOR: "red",
        }.get(event.new)
        if color:
            publish_message(topic=SET_RGB_LIGHT, message=color)
            logger.debug(f"RGB LED synced to status --> {color}")

    @observe("model:tray_toggle_clicked")
    def _on_tray_toggle_clicked(self, event):
        # The device picture is the tray button: the backend reads the
        # current tray position and moves it the other way.
        if self.model.connected:
            publish_message(topic=MOVE_TRAY, message="toggle")
            logger.info("Device picture clicked: toggling tray")

    # ---- Mechanism quick controls ------------------------------------
    # The toggles mirror the motor snapshot (*_reported, synced by the
    # model); only a click CONTRADICTING the reported state is a user
    # request. Mechanisms are not actuation, so nothing queues behind
    # realtime mode.
    @observe("model:mcu_fan_state")
    def _on_mcu_fan_changed(self, event):
        publish_message(topic=SET_FAN,
                        message=json.dumps({"board": "signal",
                                            "on": bool(event.new)}))
        logger.debug(f"MCU fan state change to {event.new} requested: "
                     f"published to {SET_FAN}")

    @observe("model:chip_locked")
    def _on_chip_locked_changed(self, event):
        if bool(event.new) == self.model.chip_locked_reported:
            return
        publish_message(topic=LOCK_CHIP, message=str(bool(event.new)))
        logger.info(f"Chip {'lock' if event.new else 'unlock'} requested")

    @observe("model:tray_out")
    def _on_tray_out_changed(self, event):
        if bool(event.new) == self.model.tray_out_reported:
            return
        publish_message(topic=MOVE_TRAY,
                        message="out" if event.new else "in")
        logger.info(f"Tray {'out' if event.new else 'in'} requested")

    @observe("model:magnet_engaged")
    def _on_magnet_engaged_changed(self, event):
        if bool(event.new) == self.model.magnet_engaged_reported:
            return
        publish_message(topic=MOVE_MAGNET,
                        message="engage" if event.new else "disengage")
        logger.info(f"Magnet {'engage' if event.new else 'disengage'} "
                    f"requested")

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
