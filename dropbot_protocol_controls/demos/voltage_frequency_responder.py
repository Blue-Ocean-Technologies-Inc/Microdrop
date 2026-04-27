"""In-process Dramatiq actor that stands in for a hardware DropBot
for protocol-driven voltage/frequency setpoint writes. Subscribes to
PROTOCOL_SET_VOLTAGE and PROTOCOL_SET_FREQUENCY, sleeps a small
'apply' delay, then publishes the matching _APPLIED ack.

Mirrors pluggable_protocol_tree/demos/electrode_responder.py.
"""

import logging
import time

import dramatiq

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from dropbot_controller.consts import (
    PROTOCOL_SET_VOLTAGE, PROTOCOL_SET_FREQUENCY,
    VOLTAGE_APPLIED, FREQUENCY_APPLIED,
)


logger = logging.getLogger(__name__)

DEMO_VF_RESPONDER_ACTOR_NAME = "ppt_demo_voltage_frequency_responder"
EXECUTOR_LISTENER_ACTOR_NAME = "pluggable_protocol_tree_executor_listener"
DEMO_APPLY_DELAY_S = 0.01  # Smaller than electrode responder; just enough to be observable.


@dramatiq.actor(actor_name=DEMO_VF_RESPONDER_ACTOR_NAME, queue_name="default")
def _demo_voltage_frequency_responder(message: str, topic: str,
                                       timestamp: float = None):
    """DropBot stand-in. Acks based on which topic the message arrived on."""
    logger.info("[demo vf responder] received %r on %s", message, topic)
    time.sleep(DEMO_APPLY_DELAY_S)

    if topic == PROTOCOL_SET_VOLTAGE:
        publish_message(message=message, topic=VOLTAGE_APPLIED)
    elif topic == PROTOCOL_SET_FREQUENCY:
        publish_message(message=message, topic=FREQUENCY_APPLIED)
    else:
        logger.warning("[demo vf responder] unknown topic %s, ignoring", topic)


def subscribe_demo_responder(router) -> None:
    """Wire the in-process voltage/frequency demo path on ``router``.

    Two subscriptions per side of the round-trip:
    1. The demo responder actor subscribes to PROTOCOL_SET_VOLTAGE /
       PROTOCOL_SET_FREQUENCY so it sees protocol writes and acks them.
    2. The executor's listener actor subscribes to VOLTAGE_APPLIED /
       FREQUENCY_APPLIED so the protocol's wait_for() unblocks when
       an ack lands.

    Without (2), wait_for would always time out — _setup_demo_hardware
    only wires the ELECTRODES_STATE_APPLIED ack for the PPT-3 electrode
    handshake. Use after a ProtocolSession has been built with
    with_demo_hardware=True if your protocol uses voltage/frequency
    columns. Importing this module already registers the dramatiq actor;
    this helper just wires the topic-to-actor subscriptions.
    """
    for topic in (PROTOCOL_SET_VOLTAGE, PROTOCOL_SET_FREQUENCY):
        router.message_router_data.add_subscriber_to_topic(
            topic=topic,
            subscribing_actor_name=DEMO_VF_RESPONDER_ACTOR_NAME,
        )
    for topic in (VOLTAGE_APPLIED, FREQUENCY_APPLIED):
        router.message_router_data.add_subscriber_to_topic(
            topic=topic,
            subscribing_actor_name=EXECUTOR_LISTENER_ACTOR_NAME,
        )
