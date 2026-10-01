# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free controller for the Device Viewer's outbound publishing: the
model @observe handlers that turn state changes into DEVICE_VIEWER_STATE_
CHANGED / DEVICE_VIEWER_GEOMETRY_CHANGED / CALIBRATION_DATA /
PHASE_NAVIGATION_MODE messages, plus the undo-stack bookkeeping those
handlers share.

This is the outbound counterpart of ``DeviceViewerMessageController``: that
one dispatches inbound topics onto the pane; this one watches the model and
publishes outbound topics. The pane flips the guard traits below
(``_disable_state_messages``, ``_undoing``, ``_applying_phase_nav_message``)
while it applies an inbound message or runs undo/redo, so the handlers here
don't re-broadcast a change that only just arrived.
"""

# Standard library imports.
import json

# Enthought library imports.
from traits.api import Bool, HasTraits, Instance, Str, observe
from traits.observation._set_change_event import SetChangeEvent
from traits.observation.events import DictChangeEvent, ListChangeEvent, TraitChangeEvent

# Microdrop package imports.
from electrode_controller.consts import electrode_state_change_publisher

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.trait_change_commands import SetChangeCommand

# Local imports.
from ..consts import (
    CALIBRATION_DATA,
    DEVICE_VIEWER_GEOMETRY_CHANGED,
    DEVICE_VIEWER_STATE_CHANGED,
    FILLER_CAPACITANCE_KEY,
    LIQUID_CAPACITANCE_KEY,
    PHASE_NAVIGATION_MODE,
)
from ..models.alpha import AlphaValue
from ..models.main_model import DeviceViewMainModel
from ..models.messages import GeometryChangedMessage
from ..utils.commands import DictChangeCommand, ListChangeCommand, TraitChangeCommand
from ..utils.message_utils import gui_models_to_message_model

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class DeviceViewerPublishController(HasTraits):
    """Own the Device Viewer's outbound publishing and the undo-stack /
    echo guards its handlers share with the pane."""

    #: Device view model whose changes drive every publish below.
    model = Instance(DeviceViewMainModel)

    #: Used to disable state messages when the model is being updated, to
    #: prevent infinite loops. Set by the pane while it applies an inbound
    #: state message.
    _disable_state_messages = Bool(False)

    #: Used to prevent changes made in undo() and redo() from being added
    #: back to the undo stack.
    _undoing = Bool(False)

    #: True while applying an inbound PHASE_NAVIGATION_MODE message, so
    #: the publish observer doesn't rebroadcast it. Set by the pane's
    #: apply_phase_navigation_mode.
    _applying_phase_nav_message = Bool(False)

    #: None means geometry never published yet.
    _last_published_id_to_channel = Instance(dict, allow_none=True)

    #: Buffer holding the serialized device-view state message, published
    #: as soon as it's written.
    message_buffer = Str()

    # ------------------------------------------------------------- undo
    def undo(self):
        """Undo the last recorded model change without re-recording it."""
        self._undoing = True

        try:
            self.model.undo_manager.undo()
        finally:
            self._undoing = False

    def redo(self):
        """Redo the last undone model change without re-recording it."""
        self._undoing = True

        try:
            self.model.undo_manager.redo()
        finally:
            self._undoing = False

    def add_traits_event_to_undo_stack(self, event):
        command = None

        if isinstance(event, TraitChangeEvent):
            command = TraitChangeCommand(event=event)
        elif isinstance(event, ListChangeEvent):
            command = ListChangeCommand(event=event)
        elif isinstance(event, DictChangeEvent):
            command = DictChangeCommand(event=event)
        elif isinstance(event, SetChangeEvent):
            command = SetChangeCommand(event=event)

        self.model.undo_manager.active_stack.push(command)

    @observe("_disable_state_messages")
    def _disable_state_messages_change_log(self, event):
        if event.new:
            logger.warning(
                "Device viewer will not be processing device view model state "
                "change since state messages are disabled."
            )
        else:
            logger.info("Device viewer will process device view model state changes")

    # ---------------------------------------------------- state message
    @observe("message_buffer")
    def publish_model_message(self, event):
        logger.debug(
            f"Buffering message for device viewer state change: {self.message_buffer}"
        )
        publish_message(topic=DEVICE_VIEWER_STATE_CHANGED, message=self.message_buffer)

    @observe(
        "model.camera_perspective.transformed_reference_rect.items, "
        "model.camera_perspective.reference_rect.items"
    )
    @observe("model.alpha_map.items.alpha")  # Observe changes to alpha values
    def model_change_handler_with_timeout(self, event=None):
        # Opacity rows a device viewer layer adds or removes are not edits.
        if isinstance(event, ListChangeEvent) and event.object is self.model.alpha_map:
            return

        if not self._undoing:
            self.add_traits_event_to_undo_stack(event)

            # The not-editable revert protects STEP state (electrodes,
            # routes, camera alignment) while a protocol runs. Alphas are
            # global display preferences, not step state — they stay
            # adjustable mid-run (like the visibility toggles, which this
            # handler never observed).
            if not self.model.editable and not isinstance(event.object, AlphaValue):
                self.undo()  # Revert changes if not editable
                return

    @observe("model.routes.layers.items.route.route.items")  # When a route is modified
    @observe(
        "model.electrodes.actuated_channels.items"
    )  # When an electrode changes state
    @observe(
        "model.electrodes.disabled_channels.items"
    )  # When an electrode is disabled/enabled
    def model_change_handler_with_message(self, event=None):
        """
        Handle changes to the model and send a message to the device viewer
        state change topic.
        """
        logger.debug(f"Model change event received: {event}")

        if self._disable_state_messages:
            return

        if self.model.route_execution_service_executing:
            # Route playback replaces actuated_channels every phase;
            # serializing + publishing the whole model per phase is
            # GUI-thread work with no consumer at that rate. The final
            # state still publishes: _cleanup flips this flag off BEFORE
            # restoring the user-toggled channels.
            return

        if not self.model.electrodes.svg_model:
            logger.warning(
                "Unable to publish device view model yet. Need svg_model to "
                "fully initialize."
            )
            return

        try:
            logger.debug("Processing device view model state change...")
            self.model_change_handler_with_timeout(event)
            self.message_buffer = gui_models_to_message_model(self.model).serialize()

            # self.publish_model_message()

        except Exception as e:
            logger.error(e, exc_info=True)

    @observe(
        "model:routes:[duration, repetitions, repeat_duration, "
        "trail_length, trail_overlay, soft_start, soft_terminate, "
        "linear_repeats, lane_left, lane_right, lanes_in_out, rotation_lock, "
        "recentre]"
    )
    def execution_params_change_handler(self, event=None):
        """Free-mode state messages carry the sidebar execution params so
        the protocol widget can seed them into an inserted step — republish
        when the user tweaks a param spinner in free mode (the
        electrode/route observer above doesn't cover the param traits).
        With a step selected the params travel via STEP_PARAMS_COMMIT
        instead. Bulk programmatic writes (apply_execution_params on step
        transition, repeats_frozen resets) run under
        _suspend_repeat_exclusion and must not publish — they would race
        the transition with stale free-mode payloads.
        """
        if self.model.step_id:
            return

        if self._disable_state_messages or self.model.routes._suspend_repeat_exclusion:
            return

        if not self.model.electrodes.svg_model:
            return

        self.message_buffer = gui_models_to_message_model(self.model).serialize()
        # self.publish_model_message()

    # ----------------------------------------------------- electrodes
    @observe("model.electrodes.actuated_channels.items")
    @observe("model.realtime_mode")
    @observe("model.connected")
    def publish_electrode_update(self, event=None):
        # Don't re-publish actuation we're applying FROM an inbound display/
        # state message (the executor's own per-phase actuation during a run)
        # back to hardware — only a genuine user actuation should. With the
        # viewer editable mid-run in Advanced Mode the apply path mutates
        # actuated_channels too, so without this guard every phase would echo
        # a redundant hardware publish (#434).
        if self._disable_state_messages:
            return

        if self.model.realtime_mode and self.model.connected:
            if (
                not self.model.protocol_running
                and (self.model.free_mode or self.model.phase_navigation_mode)
            ) or (self.model.protocol_running and self.model.editable):
                logger.info(
                    f"DEVICE VIEWER: "
                    f"publishing electrodes state change to activate "
                    f"{len(self.model.electrodes.actuated_channels)} "
                    f"channels: {self.model.electrodes.actuated_channels}"
                )
                electrode_state_change_publisher.publish(
                    self.model.electrodes.actuated_channels
                )

                return

    @observe("model.protocol_running")
    @observe("model.free_mode")
    @observe("model.phase_navigation_mode")
    @observe("model.realtime_mode")
    @observe("model.connected")
    def _actuation_publish_disabled_log_message(self, event):
        reason = ""
        if self.model.protocol_running:
            reason += "Protocol running; "

        if not self.model.free_mode and not self.model.phase_navigation_mode:
            reason += "Not in free mode or phase navigation; "

        if not self.model.realtime_mode:
            reason += "Realtime mode; "

        if not self.model.connected:
            reason += "Device Not connected; "

        logger.critical(
            f"DEVICE VIEWER: Cannot publish electrodes state change; reasons: {reason}"
        )

    # ------------------------------------------------------- geometry
    def _publish_geometry_if_changed(self):
        """Publish DEVICE_VIEWER_GEOMETRY_CHANGED if id_to_channel differs
        from the last-published mapping. No-op otherwise. Called from chip-
        insert and SVG-load handlers."""
        current = {
            eid: e.channel for eid, e in self.model.electrodes.electrodes.items()
        }

        if current == self._last_published_id_to_channel:
            return

        self._last_published_id_to_channel = dict(current)
        svg_model = self.model.electrodes.svg_model
        centroids = neighbours = None

        if svg_model is not None:
            centroids = {
                electrode_id: (polygon.centroid.x, polygon.centroid.y)
                for electrode_id, polygon in svg_model.polygons.items()
            }
            neighbours = {
                electrode_id: list(adjacent)
                for electrode_id, adjacent in svg_model.neighbours.items()
            }

        msg = GeometryChangedMessage(
            id_to_channel=current, centroids=centroids, neighbours=neighbours
        )
        publish_message(
            topic=DEVICE_VIEWER_GEOMETRY_CHANGED,
            message=msg.serialize(),
        )
        logger.info(
            f"Device Viewer: Published geometry changed event. Current id to "
            f"channel = {current}"
        )

    # ---------------------------------------------------- phase navigation
    @observe("model.phase_navigation_mode")
    def _publish_phase_navigation_mode(self, event):
        # User toggled the sidebar checkbox (or the mode was force-exited):
        # broadcast so the protocol tree's checkbox follows. Inbound messages
        # set _applying_phase_nav_message so they are not re-broadcast.
        # Assigning the model itself fires this too, with the model as
        # event.new — that is not a toggle, so it is not broadcast.
        if event.name != "phase_navigation_mode":
            return

        if not self._applying_phase_nav_message:
            publish_message(topic=PHASE_NAVIGATION_MODE, message=str(event.new))

    @observe("model.protocol_running")
    def _exit_phase_navigation_on_run(self, event):
        # A protocol run owns the hardware: force the idle mode off (this
        # publishes "False" via the observer above, unchecking both UIs).
        if event.new and self.model.phase_navigation_mode:
            self.model.phase_navigation_mode = False

    # ------------------------------------------------------- calibration
    def publish_calibration_message(self):
        """
        Publish a message with the current calibration values.
        """
        message = {
            # In pF/mm^2
            LIQUID_CAPACITANCE_KEY: self.model.liquid_capacitance_over_area,
            # In pF/mm^2
            FILLER_CAPACITANCE_KEY: self.model.filler_capacitance_over_area,
        }
        logger.warning(f"Publishing calibration message: {message}")
        publish_message(topic=CALIBRATION_DATA, message=json.dumps(message))
        logger.info(f"Published calibration message: {message}")

    @observe(
        "model.liquid_capacitance_over_area, "
        "model.filler_capacitance_over_area, model.electrode_scale"
    )
    def calibration_change_handler(self, event=None):
        """
        Handle changes to the calibration values and publish a message.
        """
        self.publish_calibration_message()
        logger.info("Calibration message published")
