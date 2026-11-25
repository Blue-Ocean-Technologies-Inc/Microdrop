# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
from functools import partial

# Enthought library imports.
from envisage.api import TASK_EXTENSIONS, ExtensionPoint, Plugin
from envisage.ui.tasks.api import TaskExtension
from pyface.action.schema.api import SchemaAddition
from pyface.api import GUI
from traits.api import Any, Instance, List, Str, on_trait_change

# Microdrop package imports.
from message_router.consts import ACTOR_TOPIC_ROUTES
from microdrop_application.consts import PKG as microdrop_application_PKG

# Microdrop utils imports.
from microdrop_utils.dramatiq_controller_base import (
    generate_class_method_dramatiq_listener_actor,
    unregister_dramatiq_listener_actor,
)

# Local imports.
from .consts import (
    ACTOR_TOPIC_DICT,
    GETTING_STARTED_TUTORIAL_HTML_PATH,
    GETTING_STARTED_TUTORIAL_ID,
    GETTING_STARTED_TUTORIAL_TITLE,
    HELP_ACTIONS_ADDITION_ID,
    HELP_LOGS_STORAGE_TUTORIAL_HTML_PATH,
    HELP_LOGS_STORAGE_TUTORIAL_TITLE,
    LISTENER_NAME,
    OPEN_TUTORIAL,
    PKG,
    TUTORIAL_ORDER_REFERENCE,
    TUTORIAL_ORDER_START,
    TUTORIALS,
    OpenTutorialRequest,
    PKG_name,
    TutorialEntry,
    help_availability_publisher,
)
from .menus import TutorialCatalog
from .simulations import TutorialSimulationCatalog

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def tutorial_sort_key(entry):
    """Order tutorials along the learning path, then by title, ignoring case."""
    return entry.order, entry.title.casefold()


class UserHelpPlugin(Plugin):
    """The Help menu, and the TUTORIALS extension point behind its submenu."""

    #### 'IPlugin' interface ##################################################

    #: The plugin unique identifier.
    id = PKG + ".plugin"

    #: The plugin name (suitable for displaying to the user).
    name = f"{PKG_name} Plugin"

    #: The task id to contribute task extension view to
    task_id_to_contribute_view = Str(default_value=f"{microdrop_application_PKG}.task")

    #### Extension points offered by this plugin ##############################

    #: Help > Tutorials entries, contributed by sibling plugins with
    #: ``List(contributes_to=TUTORIALS)``; followed while the app runs.
    tutorials = ExtensionPoint(
        List(Instance(TutorialEntry)),
        id=TUTORIALS,
        desc="Tutorial pages listed under Help > Tutorials",
    )

    #: What the Tutorials submenu shows: the contributions, in learning order.
    tutorial_catalog = Instance(TutorialCatalog, ())

    #: The simulations inside those tutorials, for the Tutorial Simulations pane.
    simulation_catalog = Instance(TutorialSimulationCatalog)

    #### Contributions to extension points made by this plugin ################

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    #: This plugin's own Help > Tutorials pages; ``tutorials`` is the
    #: extension point itself, so the contribution needs another name.
    contributed_tutorials = List(contributes_to=TUTORIALS)

    #: OPEN_TUTORIAL is routed to this plugin's listener.
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    #: The listener actor, made at start; and the last tutorial it opened,
    #: kept so its window is not garbage collected.
    _listener = Any()
    _opened = Any()

    def start(self):
        """Fill the catalog and follow tutorial contributions from now on;
        listen for OPEN_TUTORIAL, then say tutorials can be opened."""
        super().start()

        # The ``_items`` handler below fires only once this connects it.
        self.connect_extension_point_traits()
        self._update_catalog()

        # The listener exists before the announcement, so no request sent
        # in answer to it can reach an undefined actor.
        self._listener = generate_class_method_dramatiq_listener_actor(
            listener_name=LISTENER_NAME, class_method=self._listener_routine
        )
        help_availability_publisher.publish({"available": True})

    def stop(self):
        """Say tutorials can no longer be opened, and release the listener so
        a restart can register it anew."""
        help_availability_publisher.publish({"available": False})
        unregister_dramatiq_listener_actor(LISTENER_NAME)
        self._listener = None

        super().stop()

    def open_tutorial(self, tutorial_id, anchor=None):
        """Open the tutorial ``tutorial_id`` names, at the section ``anchor``
        if given, as Help > Tutorials opens it; an unknown id opens Getting
        Started instead, with a warning."""
        from .menus import tutorial_action

        entries = {entry.id: entry for entry in self.tutorial_catalog.entries}
        entry = entries.get(tutorial_id)

        if entry is None:
            logger.warning(
                f"No tutorial {tutorial_id!r}; opening Getting Started instead"
            )
            entry, anchor = entries.get(GETTING_STARTED_TUTORIAL_ID), None

        if entry is None:
            return

        self._opened = tutorial_action(entry, anchor)
        self._opened.perform(None)

    def _listener_routine(self, message, topic):

        if topic == OPEN_TUTORIAL:
            request = OpenTutorialRequest.model_validate_json(message)
            GUI.invoke_later(self.open_tutorial, request.tutorial_id, request.anchor)

    @on_trait_change("tutorials_items")
    def _on_tutorials_changed(self, event):
        """A plugin contributing tutorials was loaded or unloaded at runtime.

        The synthetic ``_items`` event needs ``on_trait_change``: observe()
        rejects the name, as no such trait exists.
        """
        logger.info(f"Tutorials changed: +{len(event.added)} -{len(event.removed)}")
        self._update_catalog()

    def _update_catalog(self):
        self.tutorial_catalog.entries = sorted(self.tutorials, key=tutorial_sort_key)

    #### Trait initializers ###################################################

    def _contributed_tutorials_default(self):
        return [
            TutorialEntry(
                title=GETTING_STARTED_TUTORIAL_TITLE,
                path=GETTING_STARTED_TUTORIAL_HTML_PATH,
                order=TUTORIAL_ORDER_START,
            ),
            TutorialEntry(
                title=HELP_LOGS_STORAGE_TUTORIAL_TITLE,
                path=HELP_LOGS_STORAGE_TUTORIAL_HTML_PATH,
                order=TUTORIAL_ORDER_REFERENCE + 10,
            ),
        ]

    def _contributed_task_extensions_default(self):
        from .menus import launcher_menu_factory, menu_factory

        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                dock_pane_factories=[self._simulations_dock_pane_factory],
                actions=[
                    SchemaAddition(
                        id=HELP_ACTIONS_ADDITION_ID,
                        factory=partial(
                            menu_factory, tutorial_catalog=self.tutorial_catalog
                        ),
                        path="MenuBar/Help",
                    ),
                    SchemaAddition(
                        factory=launcher_menu_factory,
                        path="MenuBar/Help",
                        absolute_position="last",
                    ),
                ],
            )
        ]

    def _simulation_catalog_default(self):
        return TutorialSimulationCatalog(tutorial_catalog=self.tutorial_catalog)

    def _simulations_dock_pane_factory(self, *args, **kwargs):
        from .simulations_dock_pane import TutorialSimulationsDockPane

        return TutorialSimulationsDockPane(model=self.simulation_catalog, **kwargs)
