"""GUI-side actor for the PPT-8 droplet-check failure dialog.

Subscribes to DROPLET_CHECK_DECISION_REQUEST. When fired on a Dramatiq
worker thread, marshals to the Qt main thread via a Qt Signal with
QueuedConnection (the QObject is constructed at module-import time on
the main thread), shows a styled confirm dialog via the pyface_wrapper,
and publishes the user's choice on DROPLET_CHECK_DECISION_RESPONSE.

The module-level singleton at the bottom registers the @dramatiq.actor
at import time. In production the plugin imports this module; demos
import it directly.
"""

import json

import dramatiq
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication
from traits.api import HasTraits, Instance, Str

from logger.logger_service import get_logger
from microdrop_application.dialogs.pyface_wrapper import confirm, YES
from microdrop_utils.dramatiq_controller_base import (
    generate_class_method_dramatiq_listener_actor,
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from ..consts import (
    DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME,
    DROPLET_CHECK_DECISION_RESPONSE,
)


logger = get_logger(__name__)

_REQUIRED_PAYLOAD_KEYS = ("step_uuid", "expected", "detected", "missing")


def _format_message(payload):
    """Render the dialog body. HTML markup (bold labels, <br> line
    breaks) renders correctly in BaseMessageDialog's QLabel; the handler
    can also embed HTML in `detected` entries (e.g. the bolded ERROR
    string used for backend-error surfaces) and it flows through here
    unmodified — `_fmt`'s newline-to-<br> swap keeps multi-line error
    strings readable."""
    def _fmt(seq):
        return ", ".join(str(c) for c in seq).replace("\n", "<br>") if seq else "none"
    return (
        "Droplet detection failed at the end of the step.<br><br>"
        f"<b>Expected</b>: {_fmt(payload.get('expected', []))}<br><br>"
        f"<b>Detected</b>: {_fmt(payload.get('detected', []))}<br><br>"
        f"<b>Missing</b>:  {_fmt(payload.get('missing', []))}<br><br>"
        "Continue with the protocol anyway?"
    )


class _DialogDispatcher(QObject):
    """Cross-thread bridge: emit `request_dialog` from any thread; the
    slot runs on the QObject's home thread (the main thread, since this
    is constructed at module import) via Qt.QueuedConnection."""

    request_dialog = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.request_dialog.connect(self._on_request_dialog,
                                    Qt.QueuedConnection)

    def _on_request_dialog(self, payload: dict) -> None:
        try:
            # parent=None makes the dialog top-level (independent
            # window) rather than parented to the active window —
            # avoids the dialog being hidden behind / clipped by the
            # main window during a protocol run.
            result = confirm(
                parent=None,
                message=_format_message(payload),
                title="Droplet Detection Failed",
                yes_label="Continue",
                no_label="Stay Paused",
            )
        except Exception:
            logger.exception(
                "droplet_check dialog raised; defaulting to pause"
            )
            result = None
        # pyface returns YES=30 / NO=40 / CANCEL=20 — all integer
        # constants, all truthy. Compare to YES explicitly; anything
        # else (NO, CANCEL, exception → None) is "pause", the safe
        # default. `bool(result)` would treat NO=40 as Continue.
        choice = "continue" if result == YES else "pause"
        logger.info(
            "[droplet-dialog] step %s — confirm()=%r (YES=%r) → %s",
            payload["step_uuid"], result, YES, choice,
        )
        publish_message(
            topic=DROPLET_CHECK_DECISION_RESPONSE,
            message=json.dumps({
                "step_uuid": payload["step_uuid"],
                "choice":    choice,
            }),
        )


class DropletCheckDecisionDialogActor(HasTraits):
    """Receives DROPLET_CHECK_DECISION_REQUEST, marshals to the Qt main
    thread via _DialogDispatcher, shows the confirm dialog, publishes
    the user's choice.

    Bad input (malformed JSON OR missing required keys) is logged and
    dropped. The column handler's wait_for then times out on its 24h
    decision timeout (or stop_event) — surfacing publisher bugs rather
    than masking them with a synthetic response.
    """

    listener_name = Str(DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME)
    dramatiq_listener_actor = Instance(dramatiq.Actor)
    dispatcher = Instance(_DialogDispatcher)

    def listener_actor_routine(self, message, topic):
        try:
            payload = json.loads(message)
        except (ValueError, TypeError) as exc:
            logger.warning(
                "droplet_check_decision_listener: rejecting malformed JSON %r (%s)",
                message, exc,
            )
            return

        missing = [k for k in _REQUIRED_PAYLOAD_KEYS if k not in payload]
        if missing:
            logger.warning(
                "droplet_check_decision_listener: dropping payload missing keys %r: %r",
                missing, payload,
            )
            return

        self._dispatch_to_main_thread(payload)

    def _dispatch_to_main_thread(self, payload):
        # Test seam: tests patch this to invoke the slot synchronously
        # since PySide6's Signal.emit is read-only.
        self.dispatcher.request_dialog.emit(payload)

    def traits_init(self):
        # _DialogDispatcher must be constructed on the main thread so
        # its QueuedConnection slot dispatches there. This class is
        # instantiated at module import time (singleton below), which
        # runs on the main thread in both production and demos.
        self.dispatcher = _DialogDispatcher()
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self.listener_actor_routine,
        )


# Module-import side effect: registers the @dramatiq.actor with the broker.
_dialog_actor_singleton = DropletCheckDecisionDialogActor()
