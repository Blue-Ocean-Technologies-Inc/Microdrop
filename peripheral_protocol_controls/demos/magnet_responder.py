"""In-process Dramatiq actor that stands in for the ZStage proxy
for protocol-driven magnet engage/retract. Subscribes to
PROTOCOL_SET_MAGNET, sleeps a small 'physical movement' delay, then
publishes the matching MAGNET_APPLIED ack.

Mirrors dropbot_protocol_controls.demos.voltage_frequency_responder.
"""

import json
import logging
import time

import dramatiq

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from peripheral_controller.consts import (
    PROTOCOL_SET_MAGNET, MAGNET_APPLIED,
)


logger = logging.getLogger(__name__)

DEMO_MAGNET_RESPONDER_ACTOR_NAME = "ppt_demo_magnet_responder"
EXECUTOR_LISTENER_ACTOR_NAME = "pluggable_protocol_tree_executor_listener"
DEMO_APPLY_DELAY_S = 0.05  # simulates physical magnet movement


@dramatiq.actor(actor_name=DEMO_MAGNET_RESPONDER_ACTOR_NAME, queue_name="default")
def _demo_magnet_responder(message: str, topic: str,
                            timestamp: float = None):
    """ZStage stand-in. Acks with '1' (engaged) or '0' (retracted)."""
    logger.info("[demo magnet responder] received %r on %s", message, topic)
    payload = json.loads(message)
    time.sleep(DEMO_APPLY_DELAY_S)
    publish_message(message=str(int(payload["on"])), topic=MAGNET_APPLIED)


def subscribe_demo_responder(router) -> None:
    """Wire the in-process magnet demo responder + executor listener
    on `router`. Same turnkey shape as
    dropbot_protocol_controls.demos.voltage_frequency_responder:

    1. Subscribes the demo responder to PROTOCOL_SET_MAGNET so it
       sees protocol writes and acks them.
    2. Subscribes the executor's listener actor to MAGNET_APPLIED so
       the protocol's wait_for() unblocks when the ack lands.

    Without (2), wait_for would always time out — _setup_demo_hardware
    only wires the ELECTRODES_STATE_APPLIED ack for the PPT-3
    electrode handshake. Use after a ProtocolSession has been built
    with with_demo_hardware=True.
    """
    router.message_router_data.add_subscriber_to_topic(
        topic=PROTOCOL_SET_MAGNET,
        subscribing_actor_name=DEMO_MAGNET_RESPONDER_ACTOR_NAME,
    )
    router.message_router_data.add_subscriber_to_topic(
        topic=MAGNET_APPLIED,
        subscribing_actor_name=EXECUTOR_LISTENER_ACTOR_NAME,
    )
