# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Dramatiq listener for the Device Viewer: routes each subscribed topic to an
``_on_<topic>_triggered`` handler acting on the dock pane.

Handlers run on the Dramatiq worker thread; anything touching Qt is marshalled
to the GUI thread (``GUI.invoke_later`` or a Qt signal), exactly as before.
"""

# Standard library imports.
import json
import os

# Third-party imports.
import dramatiq
from pydantic import ValidationError

# Enthought library imports.
from pyface.api import GUI
from pyface.tasks.api import TraitsDockPane
from traits.api import HasTraits, Instance, Str, provides

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import error

# Microdrop utils imports.
from microdrop_utils.datetime_helpers import TimestampedMessage
from microdrop_utils.dramatiq_controller_base import (
    basic_listener_actor_routine,
    generate_class_method_dramatiq_listener_actor,
)
from microdrop_utils.i_dramatiq_controller_base import IDramatiqControllerBase

# Local imports.
from ..consts import PKG_name, camera_controls_applied_publisher, listener_name
from ..models.media import CameraControlsRequest
from ..models.messages import DeviceViewerMessageModel
from ..utils.message_utils import gui_models_to_message_model

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def parse_camera_controls_request(message):
    """Parse and validate a DEVICE_VIEWER_CAMERA_SET_CONTROLS payload.

    Returns a ``(request, reply)`` pair: on success ``request`` is the
    validated ``CameraControlsRequest`` as a plain dict and ``reply`` is
    None; on failure ``request`` is None and ``reply`` is a ready-to-publish
    ``CameraControlsApplied`` failure payload (``ok=False``), so the caller
    can answer a waiting requester without reaching the camera widget. The
    request_id is recovered from the raw payload when possible, so the
    requester still gets matched even on a failed validation.
    """

    try:
        raw = json.loads(message) if message and message.strip() else {}
    except (json.JSONDecodeError, TypeError) as error:
        logger.warning(f"Unparseable camera controls request: {message!r}")

        return None, {"request_id": "", "ok": False, "error": str(error)}

    request_id = str(raw.get("request_id", "")) if isinstance(raw, dict) else ""

    try:
        request = CameraControlsRequest.model_validate(raw)
    except ValidationError as error:
        logger.warning(f"Invalid camera controls request: {message!r} ({error})")

        # Name the field and the reason ("exposure_ms: Input should be
        # greater than 0"), not pydantic's "1 validation error for ..." header.
        first = error.errors()[0]
        field = ".".join(str(part) for part in first["loc"]) or "request"

        return None, {
            "request_id": request_id,
            "ok": False,
            "error": f"{field}: {first['msg']}",
        }

    return request.model_dump(), None


@provides(IDramatiqControllerBase)
class DeviceViewerMessageController(HasTraits):
    """Own the Device Viewer's Dramatiq listener and its topic handlers."""

    #: Device Viewer dock pane whose model and widgets the handlers drive.
    pane = Instance(TraitsDockPane)

    #: Label used by the dispatch routine's log lines.
    name = Str(f"{PKG_name} Message Controller")

    listener_name = listener_name
    dramatiq_listener_actor = Instance(dramatiq.Actor)

    def traits_init(self):
        logger.info("Starting DeviceViewer listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name, class_method=self.listener_actor_routine
        )

    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(self, message, topic)

    # ------- Dramatiq handlers ---------------------------

    def _on_chip_inserted_triggered(self, message):
        if message.lower() == "true" and self.pane.model:
            self.pane.message_buffer = gui_models_to_message_model(
                self.pane.model
            ).serialize()
            # self.pane.publish_model_message()

    def _on_realtime_mode_updated_triggered(self, message):
        if self.pane.model:
            self.pane.model.realtime_mode = message.lower() == "true"

    def _on_phase_navigation_mode_triggered(self, message):
        GUI.invoke_later(
            self.pane._apply_phase_navigation_mode, message.lower() == "true"
        )

    def _on_phase_navigation_request_triggered(self, message):
        # Nav requests drive the route-execution service (actuated_channels +
        # its QTimer), so marshal onto the GUI thread.
        GUI.invoke_later(self._apply_phase_navigation_request, message)

    def _apply_phase_navigation_request(self, message):
        service = self.pane.model.route_execution_service if self.pane.model else None
        if service is None:
            return
        try:
            request = json.loads(message)
        except (ValueError, TypeError) as e:
            logger.warning(f"Bad phase-navigation request {message!r}: {e}")
            return
        if not isinstance(request, dict):
            logger.warning(f"Bad phase-navigation request {message!r}: not an object")
            return
        action = request.get("action")
        if action == "prev":
            service.goto_prev_phase()
        elif action == "next":
            service.goto_next_phase()
        elif action == "goto":
            try:
                index = int(request.get("index", 0))
            except (ValueError, TypeError) as e:
                logger.warning(f"Bad phase-navigation index in {message!r}: {e}")
                return
            service.goto_phase(index)
        else:
            logger.warning(f"Unknown phase-navigation action: {action!r}")

    def _on_gamepad_capture_request_triggered(self, message):
        """Relay a Gamepad-prefs remap request to the live gamepad service."""
        if self.pane.gamepad_service is not None:
            self.pane.gamepad_service.begin_button_capture(message)

    def _on_gamepad_reconnect_request_triggered(self, message):
        """Relay a manual gamepad-reconnect request to the gamepad service."""
        if self.pane.gamepad_service is not None:
            self.pane.gamepad_service.reconnect_gamepad()

    def _on_load_svg_request_triggered(self, message):
        """Load the SVG at ``message`` (a file path) into the device view.

        Lets another plugin switch devices over pub/sub instead of reaching
        into this pane. This handler runs on the Dramatiq listener's worker
        thread, but rebuilding the electrode scene touches Qt, so the actual
        work is marshalled to the GUI thread via ``GUI.invoke_later``.
        ``_set_device_view_from_svg`` already handles and reports its own
        exceptions, so there is nothing left to catch here."""
        svg_path = str(message or "").strip()
        if not svg_path or not os.path.isfile(svg_path):
            logger.warning(f"load-svg request for missing file: {svg_path!r}")
            return
        GUI.invoke_later(self.pane._set_device_view_from_svg, svg_path)

    def _on_disconnected_triggered(self, message):
        logger.debug("Disconnected from dropbot")
        self.pane.model.realtime_mode = False
        self.pane.model.connected = False

        # make interactive in case device view was disabled from a halt
        if not self.pane.device_view.isInteractive():
            self.pane.device_view.setInteractive(True)

    def _on_connected_triggered(self, message):
        logger.debug("Connected from dropbot")
        self.pane.model.connected = True

    def _on_disabled_channels_changed_triggered(self, message):
        """
        Handle hardware-reported disabled channels changes (e.g., after halted events
        or actuation discrepancies). Update the electrodes model so the UI reflects
        which channels the hardware has disabled.
        """
        if self.pane.device_viewer_advanced_preferences.allow_hardware_disables:
            data = json.loads(message)
            disabled_set = set(data.get("channels", []))
            logger.info(
                f"DEVICE VIEWER: Received disabled channels change: "
                f"{len(disabled_set)} channels disabled"
            )
            self.pane.model.electrodes.disabled_channels = disabled_set
        else:
            logger.warning(
                f"Hardware disabled channels ({message}) not applied to view. "
                f"Change behaviour in preferences/advanced settings."
            )

    def _on_halted_triggered(self, message_str):
        data = json.loads(message_str)
        name = data.get("name", "")

        if name == "output-current-exceeded":
            logger.error(
                "Output current exceeded Device viewer blocked till reconnection."
            )
            GUI.invoke_later(
                lambda: error(
                    None,
                    title="DropBot Halted",
                    message="<b>Device viewer</b>: Dropbot halt due to output current "
                    "exceeded event. Channels disabled, and re-enabling them is "
                    "blocked till reconnection.",
                )
            )
            self.pane.device_view.setInteractive(False)

    def _on_display_state_triggered(self, message_model_serial: str):
        # We send the message through a signal since Dramatiq runs the callbacks
        # in a separate thread
        # Which has weird side effects on QtGraphicsObject calls
        self.pane.device_view.display_state_signal.emit(message_model_serial)

    def _on_protocol_tree_display_state_triggered(self, message_serial: str):
        """Adapter for ProtocolTreeDisplayMessage -> DeviceViewerMessageModel.
        The downstream display_state_signal pipeline reuses what already
        works for the legacy widget."""
        from pluggable_protocol_tree.models.display_state import (
            ProtocolTreeDisplayMessage,
        )

        msg = ProtocolTreeDisplayMessage.deserialize(message_serial)
        id_to_channel = self.pane.model.electrodes.electrode_ids_channels_map
        channels_activated = {
            id_to_channel[eid]
            for eid in msg.electrodes
            if id_to_channel.get(eid) is not None
        }
        rich = DeviceViewerMessageModel(
            channels_activated=channels_activated,
            routes=[
                (route, self.pane.model.routes.get_available_color())
                for route in msg.routes
            ],
            step_info={
                "step_id": msg.step_id,
                "step_label": msg.step_label,
                "free_mode": msg.free_mode,
            },
            editable=msg.editable,
            execution_params=msg.execution_params,
        )
        self.pane.device_view.display_state_signal.emit(rich.serialize())

    def _on_protocol_running_triggered(self, message: TimestampedMessage):

        logger.debug(f"Protocol running is {message}")
        if self.pane.model:
            self.pane.model.protocol_running = (
                True if message.lower() == "true" else False
            )

    def _on_advanced_mode_change_triggered(self, message: TimestampedMessage):
        """Operator toggled Advanced Mode. While a protocol is running, this
        is what keeps the viewer editable: Advanced on -> editable (the user
        can actuate electrodes, reflected to hardware); off -> locked back to
        display. Idle editability is selection/mode-driven, so only act during
        a run (#434)."""
        advanced = message.lower() == "true"
        if self.pane.model and self.pane.model.protocol_running:
            self.pane.model.editable = advanced

    def _on_capacitance_updated_triggered(self, message):
        """
        Handle capacitance updates from the device viewer.
        """
        capacitance_str = json.loads(message).get("capacitance", None)
        if capacitance_str is not None:
            capacitance = float(capacitance_str.split("pF")[0])
            self.pane.model.last_capacitance = capacitance

    def _on_screen_capture_triggered(self, message):
        """
        Handle screen capture events from the device viewer.
        """
        logger.debug(f"Screen capture triggered: {message}")
        if self.pane.model and self.pane.camera_control_widget:
            capture_data = None
            if message and message.strip():
                try:
                    capture_data = json.loads(message)
                except (json.JSONDecodeError, TypeError):
                    logger.debug(
                        "Screen capture message is not JSON, using default capture"
                    )

            self.pane.camera_control_widget.screen_capture_signal.emit(capture_data)

    def _on_set_controls_triggered(self, message):
        """Another plugin's CameraControlsRequest (exposure/focus); applied on
        the GUI thread by the camera widget, which answers the applied
        signal itself. An invalid request is answered ok=False here instead,
        so a waiting requester fails fast rather than reaching the camera."""

        if not self.pane.camera_control_widget:
            return

        request, reply = parse_camera_controls_request(message)

        if reply is not None:
            camera_controls_applied_publisher.publish(reply)

            return

        self.pane.camera_control_widget.camera_controls_signal.emit(request)

    def _on_screen_recording_triggered(self, message):
        """
        Handle screen recording events from the device viewer.
        """
        logger.info(f"Screen recording triggered: {message}")
        if self.pane.model and self.pane.camera_control_widget:
            if not (message and message.strip()):
                return

            try:
                recording_data = json.loads(message)
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    f"Screen recording message is not valid JSON, ignoring: {message!r}"
                )
                return

            self.pane.camera_control_widget.screen_recording_signal.emit(recording_data)

    def _on_camera_active_triggered(self, message):
        """
        Handle camera activation events from the device viewer.
        """
        logger.debug(f"Camera activation triggered: {message}")
        if self.pane.model and self.pane.camera_control_widget:
            self.pane.camera_control_widget.camera_active_signal.emit(
                message.lower() == "true"
            )

    def _on_drops_detected_triggered(self, message):
        message_obj = json.loads(message)

        detected_channels = message_obj.get("detected_channels", None)

        # Apply electrode on/off states
        self.pane.model.electrodes.actuated_channels.update(detected_channels)
