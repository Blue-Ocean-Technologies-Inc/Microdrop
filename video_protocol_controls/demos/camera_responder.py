"""Demo camera responder — stands in for the real device_viewer camera
widget during PPT-6 demos. Subscribes to the three request topics
(DEVICE_VIEWER_CAMERA_ACTIVE / SCREEN_CAPTURE / SCREEN_RECORDING),
logs each event, and publishes a synthetic DEVICE_VIEWER_MEDIA_CAPTURED
ack for each capture and for each record-stop so a future media-tracker
sees realistic feedback.

Run from the demo window's routing_setup via subscribe_demo_responder.
Mirrors dropbot_protocol_controls.demos.voltage_frequency_responder.
"""

import json
import logging

import dramatiq

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from device_viewer.consts import (
    DEVICE_VIEWER_CAMERA_ACTIVE,
    DEVICE_VIEWER_SCREEN_CAPTURE,
    DEVICE_VIEWER_SCREEN_RECORDING,
    DEVICE_VIEWER_MEDIA_CAPTURED,
)


logger = logging.getLogger(__name__)

DEMO_CAMERA_RESPONDER_ACTOR_NAME = "ppt6_demo_camera_responder"


@dramatiq.actor(actor_name=DEMO_CAMERA_RESPONDER_ACTOR_NAME, queue_name="default")
def _demo_camera_responder(message: str, topic: str, timestamp: float = None):
    """Camera widget stand-in for PPT-6 demos.

    DEVICE_VIEWER_CAMERA_ACTIVE
        Just logs — camera on/off state carries no media output.

    DEVICE_VIEWER_SCREEN_CAPTURE
        Logs + publishes a synthetic image DEVICE_VIEWER_MEDIA_CAPTURED ack
        with a stable fake path keyed on step_id from the payload.

    DEVICE_VIEWER_SCREEN_RECORDING
        Logs; on action=="stop" publishes a synthetic video
        DEVICE_VIEWER_MEDIA_CAPTURED ack.
    """
    logger.info("[demo camera responder] %s -> %r", topic, message)

    if topic == DEVICE_VIEWER_SCREEN_CAPTURE:
        try:
            payload = json.loads(message)
        except (TypeError, ValueError):
            return
        publish_message(
            topic=DEVICE_VIEWER_MEDIA_CAPTURED,
            message=json.dumps({
                "path": f"/tmp/demo_capture_{payload.get('step_id', 'unknown')}.png",
                "type": "image",
            }),
        )

    elif topic == DEVICE_VIEWER_SCREEN_RECORDING:
        try:
            payload = json.loads(message)
        except (TypeError, ValueError):
            return
        if payload.get("action") == "stop":
            publish_message(
                topic=DEVICE_VIEWER_MEDIA_CAPTURED,
                message=json.dumps({
                    "path": "/tmp/demo_recording.mp4",
                    "type": "video",
                }),
            )

    # DEVICE_VIEWER_CAMERA_ACTIVE: no ack synthesised — camera state is
    # purely on/off and produces no media output.


def subscribe_demo_responder(router) -> None:
    """Wire the three request topics to the in-process demo camera responder.

    Call this from BasePluggableProtocolDemoWindow.DemoConfig.routing_setup
    after building a ProtocolSession with with_demo_hardware=True.

    Subscribes the demo actor to all three camera request topics so it sees
    every protocol write. Unlike the voltage/frequency or magnet responders,
    there is no wait_for() ack loop in the video columns (fire-and-forget),
    so no executor-listener subscription is needed.

    Mirrors dropbot_protocol_controls.demos.voltage_frequency_responder
    .subscribe_demo_responder.
    """
    for topic in (
        DEVICE_VIEWER_CAMERA_ACTIVE,
        DEVICE_VIEWER_SCREEN_CAPTURE,
        DEVICE_VIEWER_SCREEN_RECORDING,
    ):
        router.message_router_data.add_subscriber_to_topic(
            topic=topic,
            subscribing_actor_name=DEMO_CAMERA_RESPONDER_ACTOR_NAME,
        )
