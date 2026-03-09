import functools

import dramatiq

from dropbot_status_and_controls.view_helpers import RangeWithCustomViewHints
from microdrop_utils.pyface_helpers import RangeWithViewHints
from traits.api import HasTraits, Range, Bool, Button, provides, Instance, observe, Dict
from traitsui.api import View, Group, Item, UItem, HGroup, VGroup, Controller

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_controller_base import (
    IDramatiqControllerBase,
    basic_listener_actor_routine,
    generate_class_method_dramatiq_listener_actor,
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.decorators import debounce
from microdrop_utils.datetime_helpers import TimestampedMessage
from microdrop_utils.decorators import timestamped_value

from portable_dropbot_controller.consts import (
    SET_CHIP_LOCK,
    SET_LIGHT_INTENSITY,
    TOGGLE_DROPBOT_LOADING,
)

from .consts import PKG_name, listener_name


logger = get_logger(__name__)


class PortableManualControlModel(HasTraits):
    light_intensity = RangeWithCustomViewHints(
        0, 100, value=0, suffix="%",
        desc="Light intensity",
    )
    realtime_mode = Bool(False, desc="Enable or disable realtime mode")
    connected = Bool(False, desc="Connected to portable dropbot?")

    # Button traits (fire-and-forget actions)
    chip_lock = Button("Chip Lock")
    tray_toggle = Button("Tray In/Out")


PortableManualControlView = View(
    Group(
        VGroup(
            Item(
                name="light_intensity",
                resizable=True,
            ),
        ),
        HGroup(
            UItem("chip_lock", resizable=True, enabled_when="connected"),
            UItem("tray_toggle", resizable=True, enabled_when="connected"),
        ),
        show_border=True,
        padding=10,
    ),
    title=PKG_name,
    resizable=True,
)


@provides(IDramatiqControllerBase)
class PortableManualControlControl(Controller):
    # Use a dict to store the *latest* task for each topic
    message_dict = Dict()

    # IDramatiqControllerBase Interface
    dramatiq_listener_actor = Instance(dramatiq.Actor)
    name = listener_name

    def traits_init(self):
        logger.info("Starting Portable ManualControls listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=listener_name,
            class_method=self.listener_actor_routine,
        )

    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(self, message, topic)

    @timestamped_value("realtime_mode_message")
    def _on_realtime_mode_updated_triggered(self, message):
        logger.debug(f"Realtime mode updated to {message}")
        self.model.realtime_mode = message == "True"

    @timestamped_value("disconnected_message")
    def _on_disconnected_triggered(self, message):
        logger.debug("Disconnected from portable dropbot")
        self.model.realtime_mode = False
        self.model.connected = False

    @timestamped_value("disconnected_message")
    def _on_connected_triggered(self, message):
        logger.debug("Connected to portable dropbot")
        self.model.connected = True

    # Helper traits
    realtime_mode_message = Instance(TimestampedMessage)
    disconnected_message = Instance(TimestampedMessage)

    def _realtime_mode_message_default(self):
        return TimestampedMessage("", 0)

    def _disconnected_message_default(self):
        return TimestampedMessage("", 0)

    def _publish_message_if_realtime(self, topic: str, message: str) -> bool:
        if self.model.realtime_mode:
            publish_message(topic=topic, message=message)
            return True
        else:
            task = functools.partial(publish_message, topic=topic, message=message)
            logger.debug(f"QUEUEING Topic='{topic}', message={message}")
            self.message_dict[topic] = task
        return False

    def publish_queued_messages(self):
        """Processes the most recent message for each topic."""
        if not self.message_dict:
            logger.info("--- Portable Manual Control Queue empty ---")
            return

        tasks = list(self.message_dict.values())
        self.message_dict.clear()

        for task in tasks:
            try:
                task()
            except Exception as e:
                logger.warning(f"Error publishing queued message: {e}")

    # Debounced setattr
    @debounce(wait_seconds=0.3)
    def light_intensity_setattr(self, info, object, traitname, value):
        return super().setattr(info, object, traitname, value)

    @debounce(wait_seconds=1)
    def realtime_mode_setattr(self, info, object, traitname, value):
        logger.debug(f"Set realtime mode to {value}")
        info.realtime_mode.control.setChecked(value)
        return super().setattr(info, object, traitname, value)

    # Trait notification handlers

    @observe("model:realtime_mode")
    def _realtime_mode_changed(self, event):
        if event.new:
            self.publish_queued_messages()

    @observe("model:light_intensity")
    def _light_intensity_changed(self, event):
        if self._publish_message_if_realtime(
            topic=SET_LIGHT_INTENSITY, message=str(event.new)
        ):
            logger.debug(f"Requesting Light Intensity change to {event.new}%")

    @observe("model:chip_lock")
    def _chip_lock_fired(self, event):
        logger.info("Chip lock toggled")
        publish_message(topic=SET_CHIP_LOCK, message="")

    @observe("model:tray_toggle")
    def _tray_toggle_fired(self, event):
        logger.info("Tray toggle requested")
        publish_message(topic=TOGGLE_DROPBOT_LOADING, message="")


if __name__ == "__main__":
    model = PortableManualControlModel()
    view = PortableManualControlView
    handler = PortableManualControlControl(model)

    view.handler = handler

    model.configure_traits(view=view)
