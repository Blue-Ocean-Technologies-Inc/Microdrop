# enthought imports
from envisage.ids import PREFERENCES_PANES, PREFERENCES_CATEGORIES
from pyface.action.schema.schema_addition import SchemaAddition
from traits.api import List, observe

from template_status_and_controls.base_plugin import BaseStatusPlugin

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.hardware_device_monitoring_helpers import check_connected_ports_hwid
from peripheral_controller.consts import MR_BOX_HWID, START_DEVICE_MONITORING
from .consts import PKG, ACTOR_TOPIC_DICT

from logger.logger_service import get_logger

logger = get_logger(__name__)


class PeripheralUiPlugin(BaseStatusPlugin):
    """Contributes the peripheral (Z-Stage) status UI view.

    On the status-and-controls template: the base supplies the TASK_EXTENSIONS
    (dock pane + Tools menu) and ACTOR_TOPIC_ROUTES contributions; this class
    adds the preferences pane/category and the startup connection probe.
    """

    id = PKG + ".plugin"
    name = PKG.title().replace("_", " ")

    preferences_panes = List(contributes_to=PREFERENCES_PANES)
    preferences_categories = List(contributes_to=PREFERENCES_CATEGORIES)

    # ------------------------------------------------------------------ #
    # BaseStatusPlugin factory hooks                                       #
    # ------------------------------------------------------------------ #
    def _get_dock_pane_class(self):
        from .dock_pane import PeripheralStatusDockPane
        return PeripheralStatusDockPane

    def _get_actor_topic_dict(self) -> dict:
        return ACTOR_TOPIC_DICT

    def _get_menu_additions(self) -> list:
        from .menus import tools_menu_factory
        return [
            SchemaAddition(
                factory=tools_menu_factory,
                path="MenuBar/Tools",
            )
        ]

    # ------------------------------------------------------------------ #
    # Preferences contributions                                            #
    # ------------------------------------------------------------------ #
    def _preferences_panes_default(self):
        from .preferences import PeripheralPreferencesPane
        return [PeripheralPreferencesPane]

    def _preferences_categories_default(self):
        from .preferences import peripherals_tab
        return [peripherals_tab]

    # ------------------------------------------------------------------ #
    # Startup connection probe                                             #
    # ------------------------------------------------------------------ #
    @observe("application.application_initialized")
    def _on_app_initialized(self, event):
        # check if peripheral board connected
        if check_connected_ports_hwid(MR_BOX_HWID):
            logger.critical(
                "Peripheral Board Maybe Connected: Requesting Peripheral Board Search"
            )
            publish_message(message="", topic=START_DEVICE_MONITORING)
        else:
            logger.info(
                "Peripheral Board not connected. To start search, goto tools menu:"
                "Tools -> Peripherals -> Z-Stage -> Search Connection or use the peripheral UI Dock Pane button."
            )
