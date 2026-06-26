from pyface.action.schema.schema import SMenu

from microdrop_utils.dramatiq_traits_helpers import DramatiqMessagePublishAction
from peripheral_controller.consts import START_DEVICE_MONITORING as ZSTAGE_START_DEVICE_MONITORING
from heater_controller.consts import START_DEVICE_MONITORING as HEATER_START_DEVICE_MONITORING


def tools_menu_factory():
    z_stage_search = DramatiqMessagePublishAction(
        name="&Search Connection", topic=ZSTAGE_START_DEVICE_MONITORING)
    z_stage_menu = SMenu(items=[z_stage_search], id="zstage_tools", name="&Z-Stage")

    heater_search = DramatiqMessagePublishAction(
        name="&Search Connection", topic=HEATER_START_DEVICE_MONITORING)
    heater_menu = SMenu(items=[heater_search], id="heater_tools", name="&Heater")

    # Both devices listed together under the Peripherals tools menu.
    return SMenu(items=[z_stage_menu, heater_menu], id="peripherals_tools", name="Pe&ripherals")
