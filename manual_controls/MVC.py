import dramatiq
from traits.api import HasTraits, Range, Bool, provides, Instance, Str
from traitsui.api import View, Group, Item, BasicEditorFactory, Controller
from traitsui.qt.editor import Editor as QtEditor
from PySide6.QtWidgets import QPushButton

from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_controller_base import (IDramatiqControllerBase, 
                                                      basic_listener_actor_routine, 
                                                      generate_class_method_dramatiq_listener_actor)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.decorators import debounce
from microdrop_utils.timestamped_message import TimestampedMessage
from microdrop_utils.decorators import timestamped_value

from dropbot_controller.consts import SET_VOLTAGE, SET_FREQUENCY, SET_REALTIME_MODE

from .consts import PKG_name, listener_name


logger = get_logger(__name__, level="DEBUG")


class ToggleEditor(QtEditor):
    button_style_sheet = Str("QPushButton { background-color: green; font-weight: bold;"
                             "max-width: 100px; border-radius: 10px; padding: 2px;}")
    hover_style_sheet = Str("QPushButton:hover { background-color: lightgreen; }")
    
    def init(self, parent):
        self.control = QPushButton()  # The button is the control that will be displayed in the editor
        self.control.setCheckable(True)
        self.control.setChecked(self.value)
        self.control.clicked.connect(self.click_handler)

    def click_handler(self):
        '''Update the trait value to the button state. The value change will also invoke the _setattr method.'''
        self.value = self.control.isChecked() # Monitor the button state, don't simply invert self.value because it will trigger the _setattr method multiple times
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
            self.control.setStyleSheet(self.button_style_sheet + self.hover_style_sheet)
        else:
            self.control.setChecked(False)
            self.control.setText("Off")
            self.control.setStyleSheet(self.button_style_sheet.replace("green", "red") + 
                                       self.hover_style_sheet.replace("lightgreen", "lightcoral"))


class ToggleEditorFactory(BasicEditorFactory):
    # Editor is the class that actually implements your editor
    klass = ToggleEditor


class ManualControlModel(HasTraits):
    voltage = Range(
        30, 150,
        desc="the voltage to set on the dropbot device"
    )
    frequency = Range(
        100, 20000,
        desc="the frequency to set on the dropbot device"
    )
    realtime_mode = Bool(False, desc="Enable or disable realtime mode")


ManualControlView = View(
    Group(
Group(        Item(
            name='voltage',
            label='Voltage (V)',
            resizable=True,
        ),
        Item(
            name='frequency',
            label='Frequency (Hz)',
            resizable=True,
        ),
        Item(
            name='realtime_mode',
            label='Realtime Mode',
            style='custom',
            resizable=True,
            editor=ToggleEditorFactory(),
        ),), show_border=True, padding=10,
    ),
    title=PKG_name,
    resizable=True,
)


@provides(IDramatiqControllerBase)
class ManualControlControl(Controller):

    dramatiq_listener_actor = Instance(dramatiq.Actor)

    name = listener_name

    realtime_mode_message = Instance(TimestampedMessage)
    disconnected_message = Instance(TimestampedMessage)

    def __init__(self, model):
        super().__init__()
        self.model = model

    def _realtime_mode_message_default(self):
        return TimestampedMessage("", 0)
        
    def _disconnected_message_default(self):
        return TimestampedMessage("", 0)

    def voltage_setattr(self, info, object, traitname, value):
        publish_message(topic=SET_VOLTAGE, message=str(value))
        logger.debug(f"Requesting Voltage change to {value} V")
        return super().setattr(info, object, traitname, value)

    @debounce(wait_seconds=0.3)
    def frequency_setattr(self, info, object, traitname, value):
        publish_message(topic=SET_FREQUENCY, message=str(value))
        logger.debug(f"Requesting Frequency change to {value} Hz")
        return super().setattr(info, object, traitname, value)

    # This callback will not call update_editor() when it is not debounced!
    # This is likely because update_editor is only called by 'external' trait changes, and the new thread spawned by the decorator appears as such
    @debounce(wait_seconds=0.3)
    def realtime_mode_setattr(self, info, object, traitname, value):
        publish_message(
            topic=SET_REALTIME_MODE,
            message=str(value)
        )
        logger.debug(f"Set realtime mode to {value}")
        info.realtime_mode.control.setChecked(value)
        
        # info.realtime_mode.update_editor()  # You can use info to acces the editor from the ui but it's not needed when debouncing because it will call update_editor anyway
        return super().setattr(info, object, traitname, value)
  
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
        logger.debug(f"Disconnected from dropbot")
        self.model.realtime_mode = False


if __name__ == "__main__":
    model = ManualControlModel()
    view = ManualControlView
    handler = ManualControlControl(model)

    view.handler = handler

    model.configure_traits(view=view)
