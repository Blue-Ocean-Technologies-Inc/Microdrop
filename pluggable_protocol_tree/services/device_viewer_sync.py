"""DeviceViewerSyncController - bidirectional electrode sync between
the protocol tree pane and the device viewer.

Owns:
  - subscription to DEVICE_VIEWER_STATE_CHANGED (free-mode capture)
  - subscription to DEVICE_VIEWER_GEOMETRY_CHANGED (electrode->channel
    mapping cache, written to row_manager.protocol_metadata)
  - subscription to PROTOCOL_RUNNING (gate selection-driven publishes)
  - tree.selectionModel().currentChanged (selection -> DV publish)
  - publishes PROTOCOL_TREE_DISPLAY_STATE
  - the unsaved-free-mode confirm dialog and the
    'Insert as new step' RowManager.add_step call

This file is the skeleton: traits, bridge, actor, listener_routine.
Per-handler logic is added in subsequent PPT-10.2 plan tasks.
"""

from __future__ import annotations

import dramatiq

from pyface.qt.QtCore import QObject, Signal
from pyface.qt.QtWidgets import QWidget

from traits.api import Bool, Dict, HasTraits, Instance, Int, Str

from device_viewer.consts import (
    DEVICE_VIEWER_GEOMETRY_CHANGED,
    DEVICE_VIEWER_STATE_CHANGED,
    PROTOCOL_RUNNING,
)
from device_viewer.models.messages import GeometryChangedMessage
from logger.logger_service import get_logger
from microdrop_utils.dramatiq_controller_base import (
    generate_class_method_dramatiq_listener_actor,
)
from pluggable_protocol_tree.models.row_manager import RowManager

logger = get_logger(__name__)


SYNC_LISTENER_NAME = "protocol_tree_dv_sync_listener"

# Module-level so plugin start-up code can include it in the global
# actor->topic routing without instantiating a controller first.
SYNC_ACTOR_TOPIC_DICT = {
    SYNC_LISTENER_NAME: [
        DEVICE_VIEWER_STATE_CHANGED,
        DEVICE_VIEWER_GEOMETRY_CHANGED,
        PROTOCOL_RUNNING,
    ]
}


class _Bridge(QObject):
    """Qt signal bridge - Dramatiq actor runs on a worker thread, Qt
    mutations must happen on the GUI thread."""

    dv_state_received        = Signal(str)
    geometry_changed         = Signal(str)
    protocol_running_changed = Signal(bool)


class DeviceViewerSyncController(HasTraits):
    row_manager              = Instance(RowManager)
    parent_widget            = Instance(QWidget, allow_none=True)
    bridge                   = Instance(_Bridge)
    dramatiq_actor           = Instance(dramatiq.Actor, allow_none=True)
    listener_name            = Str(SYNC_LISTENER_NAME)

    _free_mode_stash         = Instance(dict, allow_none=True)
    # "" = no row selected; we never expose this trait, so the empty
    # string sentinel is fine and keeps comparisons simple.
    _last_selected_uuid      = Str()
    _protocol_running        = Bool(False)
    _suppress_publish        = Bool(False)
    # Inverted view of protocol_metadata["electrode_to_channel"]; built
    # on geometry change. The forward mapping itself lives ONLY in
    # row_manager.protocol_metadata - this dict is just an inverted
    # cache for fast free-mode reverse-lookup.
    _channel_to_id_cache     = Dict(Int, Str)
    _tree_widget             = Instance(object, allow_none=True)

    def _bridge_default(self) -> _Bridge:
        return _Bridge()

    def traits_init(self):
        if self.dramatiq_actor is None:
            self.dramatiq_actor = generate_class_method_dramatiq_listener_actor(
                listener_name=self.listener_name,
                class_method=self._listener_routine,
            )

    # --- public lifecycle ----------------------------------------------

    def attach(self, tree_widget) -> None:
        """Bind the controller to a ProtocolTreeWidget instance."""
        self._tree_widget = tree_widget
        self.bridge.geometry_changed.connect(self._on_geometry_qt)
        self.bridge.dv_state_received.connect(self._on_dv_state_qt)
        # selection wiring (Task 8)

    def detach(self) -> None:
        """Disconnect Qt signal bindings. Dramatiq broker shutdown
        handles actor teardown."""
        try:
            self.bridge.geometry_changed.disconnect(self._on_geometry_qt)
        except (RuntimeError, TypeError):
            pass
        try:
            self.bridge.dv_state_received.disconnect(self._on_dv_state_qt)
        except (RuntimeError, TypeError):
            pass
        self._tree_widget = None

    # --- single source of truth ----------------------------------------

    @property
    def id_to_channel(self) -> dict[str, int | None]:
        return self.row_manager.protocol_metadata.get(
            "electrode_to_channel", {},
        )

    # --- worker-thread dispatch (no Qt / RowManager mutation here) -----

    def _listener_routine(self, message: str, topic: str) -> None:
        if topic == DEVICE_VIEWER_STATE_CHANGED:
            self.bridge.dv_state_received.emit(message)
        elif topic == DEVICE_VIEWER_GEOMETRY_CHANGED:
            self.bridge.geometry_changed.emit(message)
        elif topic == PROTOCOL_RUNNING:
            self.bridge.protocol_running_changed.emit(
                message.casefold() == "true"
            )

    # --- Qt-thread handlers --------------------------------------------

    def _on_geometry_qt(self, payload: str) -> None:
        """Receive DEVICE_VIEWER_GEOMETRY_CHANGED on the Qt thread. Single
        write site for the electrode-to-channel mapping in protocol-tree
        land."""
        try:
            msg = GeometryChangedMessage.deserialize(payload)
        except Exception as e:
            logger.warning(f"failed to parse geometry payload {payload!r}: {e}")
            return
        stored = dict(msg.id_to_channel)
        self.row_manager.protocol_metadata["electrode_to_channel"] = stored
        self._channel_to_id_cache = {
            chan: eid for eid, chan in stored.items() if chan is not None
        }

    def _on_dv_state_qt(self, payload: str) -> None:
        """Receive DEVICE_VIEWER_STATE_CHANGED on the Qt thread. Captures
        free-mode toggles into _free_mode_stash; clears stash for any
        step-scoped or empty message."""
        from device_viewer.models.messages import DeviceViewerMessageModel
        try:
            dv_msg = DeviceViewerMessageModel.deserialize(payload)
        except Exception as e:
            logger.warning(f"failed to parse DV state: {e}")
            return

        if dv_msg.step_id:
            self._free_mode_stash = None
            return

        if not dv_msg.channels_activated and not dv_msg.routes:
            self._free_mode_stash = None
            return

        # Cold-start seed: populate metadata if empty so reverse-lookup works.
        if (not self.row_manager.protocol_metadata.get("electrode_to_channel")
                and dv_msg.id_to_channel):
            stored = dict(dv_msg.id_to_channel)
            self.row_manager.protocol_metadata["electrode_to_channel"] = stored
            self._channel_to_id_cache = {
                chan: eid for eid, chan in stored.items() if chan is not None
            }

        electrodes = sorted(
            self._channel_to_id_cache[c]
            for c in dv_msg.channels_activated
            if c in self._channel_to_id_cache
        )
        routes = [list(ids) for ids, _color in dv_msg.routes]
        self._free_mode_stash = {"electrodes": electrodes, "routes": routes}
