from pyface.action.schema.schema import SMenu

from microdrop_utils.dramatiq_traits_helpers import DramatiqMessagePublishAction
from heater_controller.consts import START_DEVICE_MONITORING


def tools_menu_factory():
    search = DramatiqMessagePublishAction(
        name="&Search Connection", topic=START_DEVICE_MONITORING)

    return SMenu(items=[search], id="heater_tools", name="&Heater")
