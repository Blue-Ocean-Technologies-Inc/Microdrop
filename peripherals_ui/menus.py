from pyface.action.schema.schema import SMenu

from microdrop_utils.dramatiq_traits_helpers import DramatiqMessagePublishAction
from peripheral_controller.consts import START_DEVICE_MONITORING


def tools_menu_factory():
    search = DramatiqMessagePublishAction(name="Search Connection", topic=START_DEVICE_MONITORING)

    # return an SMenu object compiling each object made and put into Dropbot menu under Tools menu.
    z_stage_menu = SMenu(items=[search], id="zstage_tools", name="Z-Stage")

    return SMenu(items=[z_stage_menu], id="peripherals_tools", name="Peripherals")