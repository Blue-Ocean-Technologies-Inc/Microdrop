"""GUI-side actor for the PPT-8 droplet-check failure dialog.

Subscribes to DROPLET_CHECK_DECISION_REQUEST. When fired, marshals to
the Qt main thread via QTimer.singleShot, shows a styled confirm dialog
via the pyface_wrapper, and publishes the user's choice on
DROPLET_CHECK_DECISION_RESPONSE.

The actor instance is created at plugin start (see
dropbot_protocol_controls/plugin.py); the @dramatiq.actor registration
happens at module import time via generate_class_method_dramatiq_listener_actor.

Signature note: pyface_wrapper.confirm returns YES (int=1) on confirm,
NO (int=0) on cancel — both are truthy/falsy as expected, so the
``"continue" if user_continue else "pause"`` branch works correctly.
"""

import json

import dramatiq
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from traits.api import HasTraits, Instance, Str

from logger.logger_service import get_logger
from microdrop_application.dialogs.pyface_wrapper import confirm
from microdrop_utils.dramatiq_controller_base import (
    generate_class_method_dramatiq_listener_actor,
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from ..consts import (
    DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME,
    DROPLET_CHECK_DECISION_RESPONSE,
)


logger = get_logger(__name__)


class DropletCheckDecisionDialogActor(HasTraits):
    """Receives DROPLET_CHECK_DECISION_REQUEST, shows a confirm dialog
    on the Qt main thread, publishes the user's choice."""

    listener_name = Str(DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME)
    dramatiq_listener_actor = Instance(dramatiq.Actor)

    def listener_actor_routine(self, message, topic):
        """Worker thread: parse payload, validate required keys, marshal to
        Qt thread to show dialog. Bad input (malformed JSON OR missing required
        keys) is logged + dropped — never crashes the worker, never schedules
        a Qt-thread call with a payload the dialog code can't handle.

        Dropping the message means the column handler's wait_for will time out
        on its 24h decision timeout (or on stop_event), surfacing the bug
        rather than wedging silently. Don't try to publish a synthetic 'pause'
        response on bad input — that would mask publisher bugs.
        """
        try:
            payload = json.loads(message)
        except (ValueError, TypeError) as exc:
            logger.warning(
                "droplet_check_decision_listener: rejecting malformed JSON %r (%s)",
                message, exc,
            )
            return

        required_keys = ("step_uuid", "expected", "detected", "missing")
        missing = [k for k in required_keys if k not in payload]
        if missing:
            logger.warning(
                "droplet_check_decision_listener: dropping payload missing keys %r: %r",
                missing, payload,
            )
            return

        QTimer.singleShot(0, lambda: self._show_dialog_and_respond(payload))

    def _show_dialog_and_respond(self, payload):
        """Qt main thread: show confirm dialog, publish response."""
        message = self._format_message(payload)
        try:
            user_continue = confirm(
                parent=QApplication.activeWindow(),
                message=message,
                title="Droplet Detection Failed",
                yes_label="Continue",
                no_label="Stay Paused",
            )
        except Exception:
            logger.exception("droplet_check dialog raised; defaulting to pause")
            user_continue = False
        publish_message(
            topic=DROPLET_CHECK_DECISION_RESPONSE,
            message=json.dumps({
                "step_uuid": payload["step_uuid"],
                "choice":    "continue" if user_continue else "pause",
            }),
        )

    @staticmethod
    def _format_message(payload):
        def _fmt(seq):
            return ", ".join(str(c) for c in seq) if seq else "none"
        return (
            "Droplet detection failed at the end of the step.\n\n"
            f"Expected: {_fmt(payload.get('expected', []))}\n"
            f"Detected: {_fmt(payload.get('detected', []))}\n"
            f"Missing:  {_fmt(payload.get('missing', []))}\n\n"
            "Continue with the protocol anyway?"
        )

    def traits_init(self):
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self.listener_actor_routine,
        )


# Module-level singleton — instantiating registers the actor with Dramatiq.
# Plugin import (above) brings this module in and the actor wakes up.
_dialog_actor_singleton = DropletCheckDecisionDialogActor()
