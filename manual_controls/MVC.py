from traits.api import HasTraits, Range, Bool
from traitsui.api import View, Group, Item, Controller
from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from dropbot_controller.consts import SET_VOLTAGE, SET_FREQUENCY, SET_REALTIME_MODE
from microdrop_utils.decorators import debounce
from .consts import PKG_name


logger = get_logger(__name__, level="DEBUG")


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
        Item(
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
            style='simple',
            resizable=True,
        ),
    ),
    title=PKG_name,
    resizable=True,
)


class ManualControlControl(Controller):
    @debounce(wait_seconds=0.3)
    def voltage_setattr(self, info, object, traitname, value):
        publish_message(topic=SET_VOLTAGE, message=str(value))
        logger.debug(f"Requesting Voltage change to {value} V")
        return super().setattr(info, object, traitname, value)

    @debounce(wait_seconds=0.3)
    def frequency_setattr(self, info, object, traitname, value):
        publish_message(topic=SET_FREQUENCY, message=str(value))
        logger.debug(f"Requesting Frequency change to {value} Hz")
        return super().setattr(info, object, traitname, value)

    @debounce(wait_seconds=0.5)
    def realtime_mode_setattr(self, info, object, traitname, value):
        publish_message(
            topic=SET_REALTIME_MODE,
            message=str(value)
        )
        logger.debug(f"Set realtime mode to {value}")
        return super().setattr(info, object, traitname, value)


if __name__ == "__main__":
    model = ManualControlModel()
    view = ManualControlView
    controller = ManualControlControl()

    view.handler = controller

    model.configure_traits(view=view)
