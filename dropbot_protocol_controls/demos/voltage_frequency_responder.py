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
    """Subscribe the in-process voltage/frequency responder to its
    request topics on the given MessageRouterActor.

    Use after a ProtocolSession has been built with with_demo_hardware=True
    if your protocol uses voltage/frequency columns and you want the
    setpoint roundtrip to complete in-process. Importing this module
    already registers the dramatiq actor; this helper just wires the
    topic->actor subscriptions.
    """
    router.message_router_data.add_subscriber_to_topic(
        topic=PROTOCOL_SET_VOLTAGE,
        subscribing_actor_name=DEMO_VF_RESPONDER_ACTOR_NAME,
    )
    router.message_router_data.add_subscriber_to_topic(
        topic=PROTOCOL_SET_FREQUENCY,
        subscribing_actor_name=DEMO_VF_RESPONDER_ACTOR_NAME,
    )
