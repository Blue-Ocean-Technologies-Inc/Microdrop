import functools

import dramatiq
from traits.api import HasTraits, Range, Bool, provides, Instance, observe, Dict
from traitsui.api import View, Group, Item, BasicEditorFactory, Controller
from traitsui.qt.editor import Editor as QtEditor
from PySide6.QtWidgets import QPushButton

from dropbot_controller.preferences import DropbotPreferences
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
    SET_VOLTAGE,
    SET_FREQUENCY,
    SET_REALTIME_MODE,
)
from microdrop_style.colors import GREY, SUCCESS_COLOR

from .consts import PKG_name, listener_name


logger = get_logger(__name__)


class ToggleEditor(QtEditor):
    
    def init(self, parent):
        # The button is the control that will be displayed in the editor
        self.control = QPushButton()
        self.control.setCheckable(True)
        self.control.setChecked(self.value)
        self.control.clicked.connect(self.click_handler)
        
        # Set max-width to 100px
        self.control.setMaximumWidth(100)
        
        # Apply initial styling based on current state
        self._apply_toggle_styling()
        
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
                    max-width: 100px;
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
                    max-width: 100px;
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
        # Monitor the button state, don't simply invert self.value because it will trigger the _setattr method multiple times
        self.value = self.control.isChecked()
        # This assignment and the setChecked() in update_editor keep the control.isChecked synced with the model
        # In this case, the 'isChecked' property only exists to store state in a place readable by the view, and has no visual effect

    def update_editor(self):
        '''
        Override from QtEditor. Run when the trait changes externally to the editor. 
        Default behavior is to update the label to the trait value.
       
        ATTENTION: For some reason, update_editor is called when the button is debounced, 
        but it's not called when the button is clicked.
        '''
        if self.value:
            self.control.setChecked(True)
            self.control.setText("On")
        else:
            self.control.setChecked(False)
            self.control.setText("Off")
        
        # Update styling after changing the state
        self._apply_toggle_styling()


class ToggleEditorFactory(BasicEditorFactory):
    # Editor is the class that actually implements your editor
    klass = ToggleEditor


class ManualControlModel(HasTraits):
    voltage = Range(
        30, 150, value=DropbotPreferences().default_voltage, #TODO: May need to give as input application preferences.
        desc="the voltage to set on the dropbot device (V)"
    )
    frequency = Range(
        100, 20000, value=DropbotPreferences().default_frequency, #TODO: May need to give as input application preferences.
        desc="the frequency to set on the dropbot device (Hz)"
    )
    realtime_mode = Bool(False, desc="Enable or disable realtime mode")
    connected = Bool(False, desc="Connected to dropbot?")


ManualControlView = View(
    Group(
        Group(
            Item(
                name='voltage',
                label='Voltage (V)',
                resizable=True,
                # enabled_when='realtime_mode', # we will just not publish changes instead of disabling.
            ),
            Item(
                name='frequency',
                label='Frequency (Hz)',
                resizable=True,
                # enabled_when='realtime_mode',  # we will just not publish changes instead of disabling.
            ),
            Item(
                name='realtime_mode',
                label='Realtime Mode',
                style='custom',
                resizable=True,
                editor=ToggleEditorFactory(),
                enabled_when='connected',
            ),
        ), 
        show_border=True, 
        padding=10,
        # enabled_when='connected', # will only do this for realtime mode
    ),
    title=PKG_name,
    resizable=True,
)


@provides(IDramatiqControllerBase)
class ManualControlControl(Controller):
    # Use a dict to store the *latest* task for each topic
    message_dict = Dict()

    ###################################################################################
    # IDramatiqControllerBase Interface
    ###################################################################################

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

    @timestamped_value('disconnected_message')
    def _on_connected_triggered(self, message):
        logger.debug("Connected from dropbot")
        self.model.connected = True
    ###################################################################################

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
            # Create the task "snapshot"
            task = functools.partial(publish_message, topic=topic, message=message)
            logger.debug(f"QUEUEING Topic='{topic}, message={message}' when realtime mode on")
            # Store the task, overwriting any previous task for this topic
            self.message_dict[topic] = task

        return False

    def publish_queued_messages(self):
        """
        Processes the most recent message for each topic.
        """
        logger.info("\n--- Dropbot Manual Control: Publishing Queued Messages (Last Value Only) ---")

        if not self.message_dict:
            logger.info("--- Dropbot Manual Control Queue empty ---")
            return

            # Get all the "latest" tasks that are waiting
            tasks_to_run = list(self.message_dict.values())
            # Clear the dict for the next batch
            self.message_dict.clear()

        # 5. Run the tasks *outside* the lock.
        # This is crucial for performance, as publish_message might be slow
        # and we don't want to block new messages from being queued.
        for task in self.message_dict.values():
            try:
                task()  # This executes: publish_message(topic=..., message=...)
            except Exception as e:
                # Handle potential errors during publish
                logger.warning(f"Error publishing queued message: {e}")

    ###################################################################################
    # Controller interface
    ###################################################################################

    ####### We need these voltage and frequency setattr only for debouncing. ##########
    @debounce(wait_seconds=0.3)
    def voltage_setattr(self, info, object, traitname, value):
        return super().setattr(info, object, traitname, value)

    @debounce(wait_seconds=0.3)
    def frequency_setattr(self, info, object, traitname, value):
        return super().setattr(info, object, traitname, value)

    # This callback will not call update_editor() when it is not debounced!
    # This is likely because update_editor is only called by 'external' trait changes, and the new thread spawned by the decorator appears as such
    @debounce(wait_seconds=1)
    def realtime_mode_setattr(self, info, object, traitname, value):
        logger.debug(f"Set realtime mode to {value}")
        info.realtime_mode.control.setChecked(value)
        return super().setattr(info, object, traitname, value)

    ###################################################################################
    # Trait notification handlers
    ###################################################################################

    @observe("model:realtime_mode")
    def _realtime_mode_changed(self, event):
        publish_message(
            topic=SET_REALTIME_MODE,
            message=str(event.new)
        )

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


if __name__ == "__main__":
    model = ManualControlModel()
    view = ManualControlView
    handler = ManualControlControl(model)

    view.handler = handler

    model.configure_traits(view=view)
