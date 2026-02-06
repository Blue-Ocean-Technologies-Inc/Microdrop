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
    generate_class_method_dramatiq_listener_actor
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.decorators import debounce
from microdrop_utils.datetime_helpers import TimestampedMessage
from microdrop_utils.decorators import timestamped_value

from dropbot_controller.consts import (
    SET_VOLTAGE, SET_FREQUENCY, SET_REALTIME_MODE
)
from microdrop_style.colors import GREY, SUCCESS_COLOR
from protocol_grid.consts import step_defaults

from .consts import PKG_name, listener_name

# Define topics for new controls (Adjust these strings if your backend expects different topics)
SET_CHIP_LOCK = "dropbot/requests/lock_chip"
SET_DEVICE_INSERTED = "dropbot/requests/insert_device"

logger = get_logger(__name__)


class ToggleEditor(QtEditor):

    def init(self, parent):
        # The button is the control that will be displayed in the editor
        self.control = QPushButton()
        self.control.setCheckable(True)
        self.control.setChecked(self.value)
        self.control.clicked.connect(self.click_handler)

        # Increase max-width to accommodate longer labels like "Remove Device"
        self.control.setMaximumWidth(150)

        # Apply initial styling and text
        self.update_editor()

        # Connect to button state changes to update styling
        self.control.toggled.connect(self._apply_toggle_styling)

    def _apply_toggle_styling(self):
        """Apply styling based on the button's checked state"""
        if self.control.isChecked():
            # ON state - SUCCESS_COLOR
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
                QPushButton:hover {{
                    background-color: {SUCCESS_COLOR};
                    opacity: 0.9;
                }}
                QPushButton:pressed {{
                    background-color: {SUCCESS_COLOR};
                    opacity: 0.8;
                }}
            """
        else:
            # OFF state - GREY["lighter"]
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
                QPushButton:hover {{
                    background-color: {GREY["lighter"]};
                    opacity: 0.9;
                }}
                QPushButton:pressed {{
                    background-color: {GREY["lighter"]};
                    opacity: 0.8;
                }}
            """

        self.control.setStyleSheet(style)

    def click_handler(self):
        '''Update the trait value to the button state. The value change will also invoke the _setattr method.'''
        self.value = self.control.isChecked()

    def update_editor(self):
        '''
        Override from QtEditor. Run when the trait changes externally to the editor.
        Updates label and checked state.
        '''
        # Use labels provided by the factory
        if self.value:
            self.control.setChecked(True)
            self.control.setText(self.factory.on_label)
        else:
            self.control.setChecked(False)
            self.control.setText(self.factory.off_label)

        # Update styling after changing the state
        self._apply_toggle_styling()


class ToggleEditorFactory(BasicEditorFactory):
    # Editor is the class that actually implements your editor
    klass = ToggleEditor

    # Allow custom labels for the toggle states
    on_label = Str("On")
    off_label = Str("Off")


class ManualControlModel(HasTraits):
    voltage = Range(
        30, 150, value=int(float(step_defaults["Voltage"])),
        desc="the voltage to set on the dropbot device"
    )
    frequency = Range(
        100, 20000, value=int(float(step_defaults["Frequency"])),
        desc="the frequency to set on the dropbot device"
    )

    # New traits for Chip and Device
    chip_locked = Bool(False, desc="Lock state of the chip")
    device_inserted = Bool(False, desc="Insertion state of the device")

    realtime_mode = Bool(False, desc="Enable or disable realtime mode")
    connected = Bool(False, desc="Connected to dropbot?")


ManualControlView = View(
    Group(
        # -- Vertical Group for Voltage & Frequency --
        Group(
            Item(
                name="voltage",
                label="Voltage (V)",
                resizable=True,
            ),
            Item(
                name="frequency",
                label="Frequency (Hz)",
                resizable=True,
            ),
        ),
        # -- Horizontal Group for the Buttons --
        Group(
            Item(
                name="chip_locked",
                show_label=False,
                editor=ToggleEditorFactory(
                    on_label="Unlock Chip", off_label="Lock Chip"
                ),
                enabled_when="connected",
            ),
            Item(
                name="device_inserted",
                show_label=False,
                editor=ToggleEditorFactory(
                    on_label="Remove Device", off_label="Insert Device"
                ),
                enabled_when="connected",
            ),
            Item(
                name="realtime_mode",
                show_label=False,  # Removed label to fit better horizontally
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
    # Use a dict to store the *latest* task for each topic
    message_dict = Dict()

    dramatiq_listener_actor = Instance(dramatiq.Actor)
    name = listener_name

    def traits_init(self):
        logger.info("Starting ManualControls listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=listener_name,
            class_method=self.listener_actor_routine)

    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(self, message, topic)

    @timestamped_value('realtime_mode_message')
    def _on_realtime_mode_updated_triggered(self, message):
        logger.debug(f"Realtime mode updated to {message}")
        self.model.realtime_mode = message == "True"

    @timestamped_value('disconnected_message')
    def _on_disconnected_triggered(self, message):
        logger.debug("Disconnected from dropbot")
        self.model.realtime_mode = False
        self.model.connected = False
        # Reset other states on disconnect if needed
        self.model.chip_locked = False
        self.model.device_inserted = False

    @timestamped_value('disconnected_message')
    def _on_connected_triggered(self, message):
        logger.debug("Connected from dropbot")
        self.model.connected = True

    ### Helper traits / funcs #######
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
            logger.debug(f"QUEUEING Topic='{topic}, message={message}' when realtime mode on")
            self.message_dict[topic] = task
        return False

    def publish_queued_messages(self):
        """Processes the most recent message for each topic."""
        logger.info("\n--- Dropbot Manual Control: Publishing Queued Messages ---")
        if not self.message_dict:
            logger.info("--- Dropbot Manual Control Queue empty ---")
            return

        for task in self.message_dict.values():
            try:
                task()
            except Exception as e:
                logger.warning(f"Error publishing queued message: {e}")
        self.message_dict.clear()

    ###################################################################################
    # Controller interface (SetAttr handlers)
    ###################################################################################

    @debounce(wait_seconds=0.3)
    def voltage_setattr(self, info, object, traitname, value):
        return super().setattr(info, object, traitname, value)

    @debounce(wait_seconds=0.3)
    def frequency_setattr(self, info, object, traitname, value):
        return super().setattr(info, object, traitname, value)

    @debounce(wait_seconds=1)
    def realtime_mode_setattr(self, info, object, traitname, value):
        logger.debug(f"Set realtime mode to {value}")
        # Manually force update of the editor control because debounce breaks standard flow
        info.realtime_mode.control.setChecked(value)
        return super().setattr(info, object, traitname, value)

    # New SetAttrs for Chip and Device (Debounced to prevent rapid toggling)
    @debounce(wait_seconds=0.5)
    def chip_locked_setattr(self, info, object, traitname, value):
        logger.debug(f"Set chip lock to {value}")
        info.chip_locked.control.setChecked(value)
        return super().setattr(info, object, traitname, value)

    @debounce(wait_seconds=0.5)
    def device_inserted_setattr(self, info, object, traitname, value):
        logger.debug(f"Set device inserted to {value}")
        info.device_inserted.control.setChecked(value)
        return super().setattr(info, object, traitname, value)

    ###################################################################################
    # Trait notification handlers
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
        if self._publish_message_if_realtime(topic=SET_FREQUENCY, message=str(event.new)):
            logger.debug(f"Requesting Frequency change to {event.new} Hz")

    # New Observers
    @observe("model:chip_locked")
    def _chip_locked_changed(self, event):
        # We publish this regardless of realtime mode?
        # Usually hardware switches like this should happen immediately,
        # but following your pattern, we use _publish_message_if_realtime
        # OR you can force it if these buttons should always work.
        # Assuming they act like voltage/frequency:
        if self._publish_message_if_realtime(topic=SET_CHIP_LOCK, message=str(event.new)):
            logger.debug(f"Requesting Chip Lock: {event.new}")

    @observe("model:device_inserted")
    def _device_inserted_changed(self, event):
        if self._publish_message_if_realtime(topic=SET_DEVICE_INSERTED, message=str(event.new)):
            logger.debug(f"Requesting Device Insert: {event.new}")


if __name__ == "__main__":
    model = ManualControlModel()
    view = ManualControlView
    handler = ManualControlControl(model)
    view.handler = handler
    model.configure_traits(view=view)
