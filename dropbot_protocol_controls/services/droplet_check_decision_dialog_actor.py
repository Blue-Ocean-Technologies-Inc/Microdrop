"""GUI-side actor for the PPT-8 droplet-check failure dialog.

Subscribes to DROPLET_CHECK_DECISION_REQUEST. When fired on a Dramatiq
worker thread, marshals to the Qt main thread via a Qt Signal with
Qt.QueuedConnection (the QObject is created at module-import time on
the main thread, so the connection's auto-queueing across threads
works), shows a styled confirm dialog via the pyface_wrapper, and
publishes the user's choice on DROPLET_CHECK_DECISION_RESPONSE.

The actor instance is created at plugin start (see
dropbot_protocol_controls/plugin.py); the @dramatiq.actor registration
happens at module import time via generate_class_method_dramatiq_listener_actor.

Signature note: pyface_wrapper.confirm returns YES (int=1) on confirm,
NO (int=0) on cancel — both are truthy/falsy as expected, so the
``"continue" if user_continue else "pause"`` branch works correctly.

Threading note: an earlier version used QTimer.singleShot(0, lambda: ...)
to marshal to the GUI thread. This silently failed when called from a
Dramatiq worker thread — QTimer.singleShot(msec, callable) creates the
timer in the calling thread, and worker threads have no Qt event loop,
so the dialog never showed and the column handler's wait_for hung for
24h. The Signal+QueuedConnection pattern below correctly bridges
threads and is the same shape PPT-3's actuation overlay uses
(SimpleDeviceViewer.actuation_changed).
"""

import json

import dramatiq
from PySide6.QtCore import QObject, Qt, Signal
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


class _DialogDispatcher(QObject):
    """Cross-thread bridge: Dramatiq worker emits ``request_dialog`` with
    the validated payload; the slot runs on the QObject's home thread
    (the main thread, since this is constructed at module import) via
    Qt.QueuedConnection. The slot then shows the confirm dialog and
    publishes the user's choice."""

    request_dialog = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Explicit QueuedConnection so the slot ALWAYS runs on this
        # QObject's home thread, even when emit() is called from the
        # main thread itself. Auto would work too (Qt picks Direct for
        # same-thread, Queued for cross-thread), but Queued is more
        # predictable for code that uses synchronous wait_for on the
        # other side of the round-trip.
        self.request_dialog.connect(self._on_request_dialog,
                                    Qt.QueuedConnection)

    def _on_request_dialog(self, payload: dict) -> None:
        message = _format_message(payload)
        try:
            user_continue = confirm(
                parent=QApplication.activeWindow(),
                message=message,
                title="Droplet Detection Failed",
                yes_label="Continue",
                no_label="Stay Paused",
            )
        except Exception:
            logger.exception(
                "droplet_check dialog raised; defaulting to pause"
            )
            user_continue = False
        choice = "continue" if user_continue else "pause"
        logger.info(
            "[droplet-dialog] step %s — confirm() returned %r (truthy=%s) → choice=%r",
            payload["step_uuid"], user_continue, bool(user_continue), choice,
        )
        publish_message(
            topic=DROPLET_CHECK_DECISION_RESPONSE,
            message=json.dumps({
                "step_uuid": payload["step_uuid"],
                "choice":    choice,
            }),
        )


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


class DropletCheckDecisionDialogActor(HasTraits):
    """Receives DROPLET_CHECK_DECISION_REQUEST, marshals to the Qt main
    thread via _DialogDispatcher, shows the confirm dialog, publishes
    the user's choice."""

    listener_name = Str(DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME)
    dramatiq_listener_actor = Instance(dramatiq.Actor)
    dispatcher = Instance(_DialogDispatcher)

    def listener_actor_routine(self, message, topic):
        """Worker thread: parse payload, validate required keys, emit the
        Qt signal that runs the dialog on the main thread.

        Bad input (malformed JSON OR missing required keys) is logged +
        dropped — never crashes the worker, never schedules a Qt-thread
        call with a payload the dialog code can't handle.

        Dropping the message means the column handler's wait_for will
        time out on its 24h decision timeout (or on stop_event),
        surfacing the bug rather than wedging silently. Don't try to
        publish a synthetic 'pause' response on bad input — that would
        mask publisher bugs.
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

        self._dispatch_to_main_thread(payload)

    def _dispatch_to_main_thread(self, payload):
        """Hand the validated payload to the main-thread dispatcher.

        Wrapped in its own method so tests can patch it to run the slot
        synchronously without touching PySide's read-only Signal.emit.
        """
        self.dispatcher.request_dialog.emit(payload)

    def traits_init(self):
        # The QObject must be constructed on the thread that owns the
        # main event loop. Since this class is instantiated at module
        # import time (singleton at the bottom of this file), and the
        # demo / app imports happen on the main thread, the dispatcher
        # ends up correctly bound to the main thread.
        self.dispatcher = _DialogDispatcher()
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self.listener_actor_routine,
        )


# Module-level singleton — instantiating registers the actor with Dramatiq.
# Plugin import (above) brings this module in and the actor wakes up.
_dialog_actor_singleton = DropletCheckDecisionDialogActor()
