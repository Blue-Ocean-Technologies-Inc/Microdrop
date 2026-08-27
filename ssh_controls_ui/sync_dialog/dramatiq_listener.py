# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Dramatiq listener bridging sync response topics onto SyncDialogViewModel."""
import dramatiq
from traits.api import HasTraits, provides, Instance

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_controller_base import (
    IDramatiqControllerBase,
    basic_listener_actor_routine,
    generate_class_method_dramatiq_listener_actor,
)

from .view_model import SyncDialogViewModel
from ..consts import sync_listener_name

logger = get_logger(__name__)


@provides(IDramatiqControllerBase)
class SyncDialogListener(HasTraits):
    """Separate listener so each dialog owns its own topic set.

    The SSH Key Portal dialog uses SSHControlUIListener; this listener is
    dedicated to the three SYNC_EXPERIMENTS_* response topics and
    dispatches them to ``_on_{sub_topic}_triggered`` methods on the
    SyncDialogViewModel using the standard basic_listener_actor_routine
    convention.
    """
    ui = Instance(SyncDialogViewModel)

    dramatiq_listener_actor = Instance(dramatiq.Actor)
    name = sync_listener_name

    def traits_init(self):
        logger.info("Starting sync dialog dramatiq listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=sync_listener_name,
            class_method=self.listener_actor_routine,
        )

    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(self.ui, message, topic)
