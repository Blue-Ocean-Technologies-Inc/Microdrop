"""In-process Dramatiq actor that stands in for DropletDetectionMixinService
in demos. Subscribes to DETECT_DROPLETS, publishes DROPLETS_DETECTED with
a configurable response shape so the demo can exercise success / missing /
error paths without hardware.

Mirrors voltage_frequency_responder.py shape, but with class-method state
for the switchable mode (so the Tools menu can flip between scenarios at
runtime)."""

import json
import logging

import dramatiq
from traits.api import Enum, HasTraits, Instance, Int, List, Str

from microdrop_utils.dramatiq_controller_base import (
    generate_class_method_dramatiq_listener_actor,
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from dropbot_controller.consts import DETECT_DROPLETS, DROPLETS_DETECTED


logger = logging.getLogger(__name__)

DEMO_DROPLET_RESPONDER_ACTOR_NAME = "demo_droplet_detection_responder"
EXECUTOR_LISTENER_ACTOR_NAME = "pluggable_protocol_tree_executor_listener"
"""Reference: matches what voltage_frequency_responder.py uses."""


class DropletDetectionResponder(HasTraits):
    """Configurable fake of the dropbot droplet-detection backend."""

    listener_name = Str(DEMO_DROPLET_RESPONDER_ACTOR_NAME)
    mode = Enum("succeed", "drop_one", "drop_all", "error")
    last_request_channels = List(Int)
    dramatiq_listener_actor = Instance(dramatiq.Actor)

    def listener_actor_routine(self, message, topic):
        try:
            requested = [int(c) for c in json.loads(message)]
        except (ValueError, TypeError) as exc:
            logger.warning(
                "[demo droplet responder] malformed request %r (%s); ignoring",
                message, exc,
            )
            return
        self.last_request_channels = requested

        if self.mode == "error":
            payload = {"success": False, "detected_channels": [],
                       "error": "Demo: simulated backend error"}
        elif self.mode == "drop_all":
            payload = {"success": True, "detected_channels": [], "error": ""}
        elif self.mode == "drop_one":
            # Drop the FIRST channel (responder is deterministic; demo's
            # walkthrough in the spec uses this convention).
            payload = {"success": True, "detected_channels": requested[1:],
                       "error": ""}
        else:  # "succeed"
            payload = {"success": True, "detected_channels": requested,
                       "error": ""}

        publish_message(topic=DROPLETS_DETECTED, message=json.dumps(payload))
        logger.info("[demo droplet responder] mode=%s replied %s",
                    self.mode, payload["detected_channels"])

    def traits_init(self):
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self.listener_actor_routine,
        )

    def subscribe(self, router):
        """Wire the responder + executor listener for the round-trip on
        ``router``. Must be called from the demo's routing_setup."""
        # 1. Responder subscribes to DETECT_DROPLETS so it sees the request.
        router.message_router_data.add_subscriber_to_topic(
            topic=DETECT_DROPLETS,
            subscribing_actor_name=self.listener_name,
        )
        # 2. Executor's listener subscribes to DROPLETS_DETECTED + the
        # decision-response topic so the handler's wait_for unblocks.
        from dropbot_protocol_controls.consts import (
            DROPLET_CHECK_DECISION_RESPONSE,
        )
        for topic in (DROPLETS_DETECTED, DROPLET_CHECK_DECISION_RESPONSE):
            router.message_router_data.add_subscriber_to_topic(
                topic=topic,
                subscribing_actor_name=EXECUTOR_LISTENER_ACTOR_NAME,
            )
        # 3. The dialog actor subscribes to DROPLET_CHECK_DECISION_REQUEST
        # via ACTOR_TOPIC_DICT in production. In the demo we manually wire
        # it (no MessageRouterPlugin lifecycle in demos).
        from dropbot_protocol_controls.consts import (
            DROPLET_CHECK_DECISION_REQUEST,
            DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME,
        )
        router.message_router_data.add_subscriber_to_topic(
            topic=DROPLET_CHECK_DECISION_REQUEST,
            subscribing_actor_name=DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME,
        )
