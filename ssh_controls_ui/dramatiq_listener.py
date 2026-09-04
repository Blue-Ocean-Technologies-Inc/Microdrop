# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import dramatiq

from traits.api import HasTraits, Instance, provides

from microdrop_utils.dramatiq_controller_base import (
    IDramatiqControllerBase,
    assert_handlers_exist_for_topics,
    basic_listener_actor_routine,
    generate_class_method_dramatiq_listener_actor,
)

from .consts import ACTOR_TOPIC_DICT, listener_name
from .view_model import SSHControlViewModel

from logger.logger_service import get_logger

logger = get_logger(__name__)


@provides(IDramatiqControllerBase)
class SSHControlUIListener(HasTraits):
    ui = Instance(SSHControlViewModel)

    ###################################################################################
    # IDramatiqControllerBase Interface
    ###################################################################################

    dramatiq_listener_actor = Instance(dramatiq.Actor)
    name = listener_name

    def traits_init(self):
        logger.info("Starting SSH controls UI listener")
        # basic_listener_actor_routine dispatches to self.ui, not self, so the
        # #617 startup check must target self.ui directly rather than going
        # through generate_class_method_dramatiq_listener_actor's topics= hook.
        assert_handlers_exist_for_topics(self.ui, ACTOR_TOPIC_DICT[listener_name])
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=listener_name, class_method=self.listener_actor_routine
        )

    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(self.ui, message, topic)
