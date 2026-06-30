from pyface.action.schema.schema import SMenu
from pyface.tasks.action.api import DockPaneAction

from microdrop_utils.dramatiq_traits_helpers import DramatiqMessagePublishAction

from .consts import PKG, START_DEVICE_MONITORING


def heater_tools_menu_factory():
    """Tools ▸ Heater ▸ {Search Connection, Configure Sensors & Heaters}."""
    search = DramatiqMessagePublishAction(
        name="&Search Connection", topic=START_DEVICE_MONITORING)
    # Opens the modal configurator on the heater dock pane (DockPaneAction
    # resolves the pane by id and calls the method).
    configure = DockPaneAction(
        id="heater_configure_sensors",
        dock_pane_id=PKG + ".dock_pane",
        name="&Configure Sensors && Heaters",
        method="open_sensor_config",
    )
    return SMenu(items=[search, configure], id="heater_tools", name="&Heater")

def tools_menu_factory():
    # The heater contributes its own Tools -> Peripherals -> Heater
    return SMenu(items=[heater_tools_menu_factory()], id="peripherals_tools", name="&Peripherals")
