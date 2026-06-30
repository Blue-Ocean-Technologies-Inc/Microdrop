from pyface.action.schema.schema import SMenu

from microdrop_utils.dramatiq_traits_helpers import DramatiqMessagePublishAction
from peripheral_controller.consts import START_DEVICE_MONITORING as ZSTAGE_START_DEVICE_MONITORING

def z_stage_menu_factory():
    z_stage_search = DramatiqMessagePublishAction(
        name="&Search Connection", topic=ZSTAGE_START_DEVICE_MONITORING)
    z_stage_menu = SMenu(items=[z_stage_search], id="zstage_tools", name="&Z-Stage")

    return z_stage_menu

def tools_menu_factory():
    return SMenu(items=[z_stage_menu_factory()], id="peripherals_tools", name="&Peripherals")
