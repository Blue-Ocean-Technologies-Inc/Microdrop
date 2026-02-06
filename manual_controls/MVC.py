import functools

import dramatiq
from traits.api import HasTraits, Range, Bool, provides, Instance, observe, Dict, Str
from traitsui.api import View, Group, Item, BasicEditorFactory, Controller
from traitsui.qt.editor import Editor as QtEditor
from PySide6.QtWidgets import QPushButton

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

from dropbot_controller.consts import SET_VOLTAGE, SET_FREQUENCY, SET_REALTIME_MODE
from microdrop_style.colors import GREY, SUCCESS_COLOR
from protocol_grid.consts import step_defaults

from .consts import PKG_name, listener_name

# Define topics for new controls
SET_CHIP_LOCK = "dropbot/requests/lock_chip"
SET_LIGHT_INTENSITY = "dropbot/requests/set_light_intensity"

logger = get_logger(__name__)


class ToggleEditor(QtEditor):

    def init(self, parent):
        self.control = QPushButton()
        self.control.setCheckable(True)
        self.control.setChecked(self.value)
        self.control.clicked.connect(self.click_handler)
        self.control.setMaximumWidth(150)
        self.update_editor()
        self.control.toggled.connect(self._apply_toggle_styling)

    def _apply_toggle_styling(self):
        """Apply styling based on the button's checked state"""
        # If the widget is disabled (waiting for response), we might want a different look.
        # However, standard Qt disabled styling (greyed out) usually applies automatically
        # when the Item is disabled via enabled_when.

        if self.control.isChecked():
            style = f"""
                QPushButton {{
                    background-color: {SUCCESS_COLOR};
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-weight: bold;
                    max-width: 150px;
                }}
            """
        else:
            style = f"""
                QPushButton {{
                    background-color: {GREY["lighter"]};
                    color: #333333;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-weight: bold;
                    max-width: 150px;
                }}
            """
        # Note: We rely on standard Qt behavior for the "disabled" visual state
        self.control.setStyleSheet(style)

    def click_handler(self):
        self.value = self.control.isChecked()

    def update_editor(self):
        if self.value:
            self.control.setChecked(True)
            self.control.setText(self.factory.on_label)
        else:
            self.control.setChecked(False)
            self.control.setText(self.factory.off_label)
        self._apply_toggle_styling()


class ToggleEditorFactory(BasicEditorFactory):
    klass = ToggleEditor
    on_label = Str("On")
    off_label = Str("Off")


class ManualControlModel(HasTraits):
    voltage = Range(
        30,
        150,
        value=int(float(step_defaults["Voltage"])),
        desc="the voltage to set on the dropbot device",
    )
    frequency = Range(
        100,
        20000,
        value=int(float(step_defaults["Frequency"])),
        desc="the frequency to set on the dropbot device",
    )

    # --- Data Traits ---
    chip_locked = Bool(False, desc="Lock state of the chip")

    # --- UI Enable State Traits ---
    # These control whether the user can click the buttons
    chip_locked_enabled = Bool(True)

    realtime_mode = Bool(False, desc="Enable or disable realtime mode")
    connected = Bool(False, desc="Connected to dropbot?")

    # Light Controls
    light_intensity = Range(0, 100, value=100, desc="Light intensity percentage")
    lights_on = Bool(False, desc="Master toggle for lights")


ManualControlView = View(
    Group(
        Group(
            Item(name="voltage", label="Voltage (V)", resizable=True),
            Item(name="frequency", label="Frequency (Hz)", resizable=True),
            Item(
                name="light_intensity",
                label="Light Intensity (%)",
                resizable=True,
                enabled_when="lights_on",
            ),
        ),
        Group(
            Item(
                name="chip_locked",
                show_label=False,
                editor=ToggleEditorFactory(
                    on_label="Chip Locked", off_label="Chip Unlocked"
                ),
                # Disabled if disconnected OR waiting for response
                enabled_when="connected and chip_locked_enabled",
            ),
            Item(
                name="lights_on",
                show_label=False,
                editor=ToggleEditorFactory(
                    on_label="Lights: On", off_label="Lights: Off"
                ),
                # Disable button while waiting for light intensity confirmation
                enabled_when="connected",
            ),
            Item(
                name="realtime_mode",
                show_label=False,
                editor=ToggleEditorFactory(
                    on_label="Realtime: On", off_label="Realtime: Off"
                ),
                enabled_when="connected",
            ),
            orientation="horizontal",
            show_border=False,
        ),
        show_border=True,
        padding=10,
    ),
    title=PKG_name,
    resizable=True,
)


@provides(IDramatiqControllerBase)
class ManualControlControl(Controller):
    message_dict = Dict()
    dramatiq_listener_actor = Instance(dramatiq.Actor)
    name = listener_name

    def traits_init(self):
        logger.info("Starting ManualControls listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=listener_name, class_method=self.listener_actor_routine
        )

    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(self, message, topic)

    ### --- Helper traits / funcs ---
    realtime_mode_message = Instance(TimestampedMessage)
    disconnected_message = Instance(TimestampedMessage)

    # These store the raw messages for the new listeners
    chip_locked_message = Instance(TimestampedMessage)

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
            logger.debug(
                f"QUEUEING Topic='{topic}, message={message}' when realtime mode on"
            )
            self.message_dict[topic] = task
        return False

    def publish_queued_messages(self):
        logger.info("--- Dropbot Manual Control: Publishing Queued Messages ---")
        if not self.message_dict:
            return
        for task in self.message_dict.values():
            try:
                task()
            except Exception as e:
                logger.warning(f"Error publishing queued message: {e}")
        self.message_dict.clear()

    ###################################################################################
    # Connection Handlers
    ###################################################################################
    @timestamped_value("disconnected_message")
    def _on_disconnected_triggered(self, message):
        logger.debug("Disconnected from dropbot")
        self.model.connected = False
        self.model.realtime_mode = False
        self.model.chip_locked = False

        # Reset enable states on disconnect just in case
        self.model.chip_locked_enabled = True

    @timestamped_value("disconnected_message")
    def _on_connected_triggered(self, message):
        logger.debug("Connected to dropbot")
        self.model.connected = True

    @timestamped_value("realtime_mode_message")
    def _on_realtime_mode_updated_triggered(self, message):
        self.model.realtime_mode = message == "True"

    ###################################################################################
    # RESPONSE LISTENERS (Unlock the UI here)
    ###################################################################################

    def _on_chip_inserted_triggered(self, message):
        """Called when the backend confirms the device loaded state."""
        confirmed_state = str(message).lower() == "true"
        logger.debug(f"Confirmation received: Device Loaded = {confirmed_state}")

        # Update the value to what the hardware confirmed
        self.model.chip_locked = confirmed_state

        # Re-enable the button
        self.model.chip_locked_enabled = True

    ###################################################################################
    # SetAttr handlers (UI Click Handlers)
    ###################################################################################

    @debounce(wait_seconds=0.3)
    def voltage_setattr(self, info, object, traitname, value):
        return super().setattr(info, object, traitname, value)

    @debounce(wait_seconds=0.3)
    def frequency_setattr(self, info, object, traitname, value):
        return super().setattr(info, object, traitname, value)

    @debounce(wait_seconds=0.1)
    def light_intensity_setattr(self, info, object, traitname, value):
        return super().setattr(info, object, traitname, value)

    @debounce(wait_seconds=0.5)
    def lights_on_setattr(self, info, object, traitname, value):
        info.lights_on.control.setChecked(value)
        return super().setattr(info, object, traitname, value)

    @debounce(wait_seconds=1)
    def realtime_mode_setattr(self, info, object, traitname, value):
        info.realtime_mode.control.setChecked(value)
        return super().setattr(info, object, traitname, value)

    @debounce(wait_seconds=0.5)
    def chip_locked_setattr(self, info, object, traitname, value):
        logger.debug(f"User clicked Chip Lock -> Requesting: {value}")

        # 1. Disable the button immediately to prevent double clicks
        info.object.chip_locked_enabled = False

        # 2. Force visual update of the button (debounce can sometimes lag)
        info.chip_locked.control.setChecked(value)

        # 3. Proceed with setting the attribute (triggers _chip_locked_changed)
        return super().setattr(info, object, traitname, value)

    ###################################################################################
    # Trait Observers (Send Requests)
    ###################################################################################

    @observe("model:realtime_mode")
    def _realtime_mode_changed(self, event):
        publish_message(topic=SET_REALTIME_MODE, message=str(event.new))
        if event.new:
            self.publish_queued_messages()

    @observe("model:voltage")
    def _voltage_changed(self, event):
        if self._publish_message_if_realtime(topic=SET_VOLTAGE, message=str(event.new)):
            logger.debug(f"Requesting Voltage change to {event.new} V")

    @observe("model:frequency")
    def _frequency_changed(self, event):
        if self._publish_message_if_realtime(
            topic=SET_FREQUENCY, message=str(event.new)
        ):
            logger.debug(f"Requesting Frequency change to {event.new} Hz")

    @observe("model:chip_locked")
    def _chip_locked_changed(self, event):
        if not self.model.chip_locked_enabled:
            publish_message(topic=SET_CHIP_LOCK, message=str(event.new))

    @observe("model:light_intensity")
    def _light_intensity_changed(self, event):
        # Publish the new intensity
        msg = str(event.new)
        publish_message(topic=SET_LIGHT_INTENSITY, message=msg)
        logger.info(f"Requesting Light Intensity: {event.new}")

    @observe("model:lights_on")
    def _lights_on_changed(self, event):
        if event.new:
            publish_message(
                topic=SET_LIGHT_INTENSITY, message=str(self.model.light_intensity)
            )
        else:
            publish_message(
                topic=SET_LIGHT_INTENSITY, message="0"
            )


if __name__ == "__main__":
    model = ManualControlModel()
    view = ManualControlView
    handler = ManualControlControl(model)
    view.handler = handler
    model.configure_traits(view=view)
