"""
BaseStatusPlugin — Envisage plugin wiring for device status-and-controls panels.

Every device panel plugin needs the same Envisage boilerplate:
  - contributed_task_extensions  (dock pane + optional menu items)
  - actor_topic_routing          (Dramatiq topic subscriptions)

Subclasses provide the device-specific pieces through factory methods,
keeping the Envisage machinery out of each device module.

Design notes:
  - _get_actor_topic_dict() is a factory method rather than a class attribute
    so that subclasses only need to override one small method instead of
    redefining the entire actor_topic_routing List trait.
  - _get_menu_additions() returns an empty list by default so plugins that
    don't need menus (e.g. OpenDrop) require zero extra code.
"""

from traits.api import List, Str
from envisage.api import Plugin, TASK_EXTENSIONS
from envisage.ui.tasks.api import TaskExtension

from microdrop_application.consts import PKG as microdrop_application_PKG
from message_router.consts import ACTOR_TOPIC_ROUTES

from logger.logger_service import get_logger

logger = get_logger(__name__)


class BaseStatusPlugin(Plugin):
    """
    Base Envisage plugin for device status-and-controls panels.

    Minimal subclass example
    ------------------------
    ::

        class MyDevicePlugin(BaseStatusPlugin):
            id   = MyPKG + ".plugin"
            name = f"{MyPKG_name} Plugin"

            def _get_dock_pane_class(self):
                from .dock_pane import MyDeviceDockPane
                return MyDeviceDockPane

            def _get_actor_topic_dict(self) -> dict:
                from .consts import ACTOR_TOPIC_DICT
                return ACTOR_TOPIC_DICT

    Adding menu items
    -----------------
    ::

            def _get_menu_additions(self) -> list:
                from pyface.action.schema.schema_addition import SchemaAddition
                from .menus import menu_factory
                return [
                    SchemaAddition(
                        factory=menu_factory,
                        before="TaskToggleGroup",
                        path="MenuBar/View",
                    )
                ]
    """

    #: Target task that this plugin's dock pane and menus are added to.
    task_id_to_contribute_view = Str(default_value=f"{microdrop_application_PKG}.task")

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)
    actor_topic_routing = List(contributes_to=ACTOR_TOPIC_ROUTES)

    # ------------------------------------------------------------------ #
    # Trait defaults                                                        #
    # ------------------------------------------------------------------ #

    def _contributed_task_extensions_default(self):
        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                dock_pane_factories=[self._get_dock_pane_class()],
                actions=self._get_menu_additions(),
            )
        ]

    def _actor_topic_routing_default(self):
        return [self._get_actor_topic_dict()]

    # ------------------------------------------------------------------ #
    # Factory hooks — implement / override in subclass                     #
    # ------------------------------------------------------------------ #

    def _get_dock_pane_class(self):
        """
        Return the concrete dock pane class for this device.

        Raises NotImplementedError if not overridden.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement _get_dock_pane_class()"
        )

    def _get_actor_topic_dict(self) -> dict:
        """
        Return the ACTOR_TOPIC_DICT that maps listener name → topic list.

        This is registered with the message router so the listener receives
        the correct pub/sub topics. Raises NotImplementedError if not overridden.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement _get_actor_topic_dict()"
        )

    def _get_menu_additions(self) -> list:
        """
        Return a list of SchemaAddition objects to add to the menu bar.

        Default: empty list (no menus). Override to add device-specific menus.
        """
        return []
