# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Envisage plugin of the Portable DropBot self-test hub (frontend)."""

# Standard library imports.
from functools import partial

# Enthought library imports.
from envisage.api import TASK_EXTENSIONS, Plugin
from envisage.ui.tasks.api import TaskExtension
from pyface.action.schema.api import SchemaAddition
from traits.api import Instance, List, Str

# Microdrop package imports.
from message_router.consts import ACTOR_TOPIC_ROUTES
from microdrop_application.consts import PKG as microdrop_application_PKG

# Local imports.
from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name


class PortableDropbotSelfTestsPlugin(Plugin):
    """Contributes Tools > Self Tests... and owns the hub's model and
    listener for the whole session: the panel can be closed and reopened
    mid-run, or after a run, and still shows its state."""

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    #: The task the Tools menu entry is contributed to.
    task_id_to_contribute_view = Str(f"{microdrop_application_PKG}.task")

    #: The hub's state; made in start(), dropped in stop().
    model = Instance(
        "portable_dropbot_self_tests.models.self_tests_model.SelfTestHubModel"
    )

    #: The panel's one controller, reused for every open so the model's
    #: buttons have a single set of observers; made in start().
    controller = Instance(
        "portable_dropbot_self_tests.controllers.self_tests_controller."
        "SelfTestHubController"
    )

    #: Feeds the self-test signals to model; made in start().
    message_handler = Instance(
        "portable_dropbot_self_tests.message_handlers.self_tests_message_handler."
        "SelfTestsMessageHandler"
    )

    def _contributed_task_extensions_default(self):
        from .menus import self_tests_group_factory

        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                actions=[
                    SchemaAddition(
                        id=f"{PKG}.self_tests_addition",
                        factory=partial(self_tests_group_factory, self),
                        path="MenuBar/Tools",
                    )
                ],
            )
        ]

    def start(self):
        from .controllers.self_tests_controller import SelfTestHubController
        from .message_handlers.self_tests_message_handler import (
            SelfTestsMessageHandler,
        )
        from .models.self_tests_model import SelfTestHubModel

        self.model = SelfTestHubModel()
        self.controller = SelfTestHubController(model=self.model)
        self.message_handler = SelfTestsMessageHandler(model=self.model)

    def stop(self):
        if self.controller is not None:
            self.controller.close_panel()
            self.controller = None

        if self.message_handler is not None:
            self.message_handler.teardown()
            self.message_handler = None

        self.model = None
