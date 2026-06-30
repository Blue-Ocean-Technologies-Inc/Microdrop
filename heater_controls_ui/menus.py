from pyface.action.schema.schema import SMenu

from microdrop_utils.dramatiq_traits_helpers import DramatiqMessagePublishAction

from .consts import START_DEVICE_MONITORING


def heater_tools_menu_factory():
    """Tools ▸ Heater ▸ Search Connection — triggers a heater connection scan
    (the same action the status-bar heater icon performs on click)."""
    search = DramatiqMessagePublishAction(
        name="&Search Connection", topic=START_DEVICE_MONITORING)
    return SMenu(items=[search], id="heater_tools", name="&Heater")

def tools_menu_factory():
    # The heater contributes its own Tools -> Peripherals -> Heater
    return SMenu(items=[heater_tools_menu_factory()], id="peripherals_tools", name="&Peripherals")
