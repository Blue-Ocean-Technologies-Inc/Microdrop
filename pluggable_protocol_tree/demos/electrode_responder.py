# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""In-process Dramatiq actor that stands in for a hardware electrode
controller. Subscribes to ELECTRODES_STATE_CHANGE, sleeps a small
'apply' delay, then publishes ELECTRODES_STATE_APPLIED.

The demo's run_widget.py registers this actor's subscription with the
message router and starts a Dramatiq worker so it actually fires.
"""

import logging
import time

import dramatiq

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED,
)


logger = logging.getLogger(__name__)

DEMO_RESPONDER_ACTOR_NAME = "ppt_demo_electrode_responder"
DEMO_APPLY_DELAY_S = 0.05


@dramatiq.actor(actor_name=DEMO_RESPONDER_ACTOR_NAME, queue_name="default")
def _demo_electrode_responder(message: str, topic: str,
                               timestamp: float = None):
    """Hardware-controller stand-in. ~50ms apply delay, acks."""
    logger.info("[demo electrode responder] received %r on %s", message, topic)
    time.sleep(DEMO_APPLY_DELAY_S)
    publish_message(message="ok", topic=ELECTRODES_STATE_APPLIED)
