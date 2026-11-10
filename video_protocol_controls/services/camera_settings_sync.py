# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Keeps the selected protocol step's camera setup (the Capture column's
capture_camera_settings cell) and the device viewer's camera in step — the
Capture column's counterpart of the fluorescence pane's "pane follows step":

- a user edit in the camera panel (a CameraSettingsSnapshot with
  user_edit) is stored into the selected steps over PROTOCOL_TREE_SET_CELL:
  into the current step when it captures, into every other selected step
  only when it already holds a setup (only_if_set) — so a multi-step
  selection edits all of their setups at once;
- a capturing step without a setup yet gets the panel's current one;
- selecting a step that holds a setup applies it to the camera
  (CameraSettingsRequest), and so does selecting another camera while such
  a step is selected — the device viewer warns about what that camera
  cannot take.

Idle only: during a run the Capture handler applies each step's setup, and
the tree refuses set-cell. Qt-free; the handlers run on Dramatiq worker
threads, serialized by a lock.
"""

# Standard library imports.
import json
import threading
import uuid

# Third-party imports.
import dramatiq

# Enthought library imports.
from traits.api import Any, Bool, HasTraits, Instance, List, Str

# Microdrop package imports.
from device_viewer.consts import (
    DEVICE_VIEWER_CAMERA_SETTINGS,
    PROTOCOL_RUNNING,
    camera_apply_settings_publisher,
)
from pluggable_protocol_tree.consts import (
    PROTOCOL_TREE_ROW_SELECTED,
    protocol_tree_set_cell_publisher,
)
from pluggable_protocol_tree.models.cell_sync import ProtocolTreeRowSelectedMessage

# Microdrop utils imports.
from microdrop_utils.dramatiq_controller_base import (
    generate_class_method_dramatiq_listener_actor,
)

# Local imports.
from ..consts import (
    CAMERA_SETTINGS_SYNC_LISTENER_NAME,
    CAPTURE_CAMERA_SETTINGS_FIELD_ID,
    CAPTURE_FIELD_ID,
)
from ..protocol_columns.capture_column import normalize_camera_settings

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class CameraSettingsSync(HasTraits):
    """See the module docstring."""

    listener_name = Str(CAMERA_SETTINGS_SYNC_LISTENER_NAME)

    dramatiq_listener_actor = Instance(dramatiq.Actor)

    #: The device viewer's latest CameraSettings (without user_edit); None
    #: before its first snapshot.
    camera_settings = Any()

    #: The tree's current step's uuid; None for no step or a group.
    step_id = Any()

    #: The current step's number and name, for the user's warnings.
    step_label = Str()

    #: The current step captures.
    step_captures = Bool(False)

    #: The current step's stored camera setup, or None.
    step_settings = Any()

    #: Every selected step's uuid (the current one included).
    selected_step_ids = List(Str)

    protocol_running = Bool(False)

    #: (step uuid, setup) last applied to the camera or stored from it, so
    #: the tree's rebroadcast of our own write is not applied back.
    _synced = Any()

    #: Serializes the handlers across Dramatiq worker threads (Any, not
    #: Instance(threading.Lock): Python 3.12 rejects a lock there).
    _lock = Any()

    def traits_init(self):
        self._lock = threading.Lock()
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self.listener_actor_routine,
        )

    def listener_actor_routine(self, message, topic):
        with self._lock:
            if topic == PROTOCOL_RUNNING:
                self._on_protocol_running(message)
            elif topic == PROTOCOL_TREE_ROW_SELECTED:
                self._on_row_selected(message)
            elif topic == DEVICE_VIEWER_CAMERA_SETTINGS:
                self._on_camera_settings(message)

    # ------------------------------------------------------------------ #
    # Topic handlers                                                       #
    # ------------------------------------------------------------------ #

    def _on_protocol_running(self, message):
        self.protocol_running = str(message).lower() == "true"

        # The run left the camera on its last step's setup: the next
        # selection applies its step's setup again.
        if not self.protocol_running:
            self._synced = None

    def _on_row_selected(self, message):
        """Track the selection; a capturing step's setup goes to the camera,
        or the camera's to a capturing step without one."""

        try:
            msg = ProtocolTreeRowSelectedMessage.deserialize(str(message))
        except ValueError as error:
            logger.warning(f"Unparseable row-selected payload: {error}")

            return

        self.step_id = msg.step_id
        self.selected_step_ids = msg.selected_step_ids or (
            [msg.step_id] if msg.step_id else []
        )
        self.step_captures = bool(msg.cells.get(CAPTURE_FIELD_ID))
        self.step_settings = msg.cells.get(CAPTURE_CAMERA_SETTINGS_FIELD_ID)
        self.step_label = _step_label(msg.cells)

        if self.protocol_running or not self.step_id or not self.step_captures:
            return

        if self.step_settings is None:
            self._store_camera_settings()

            return

        self._apply_step_settings()

    def _on_camera_settings(self, message):
        """Keep the camera's setup; store a user edit into the selected
        steps, and apply the current step's setup to a newly selected
        camera."""

        try:
            snapshot = json.loads(message)
        except (TypeError, ValueError) as error:
            logger.warning(f"Unparseable camera settings payload: {error}")

            return

        user_edit = bool(snapshot.pop("user_edit", False))
        previous_camera = (self.camera_settings or {}).get("camera")
        self.camera_settings = normalize_camera_settings(snapshot)

        if self.protocol_running or not self.step_id or self.camera_settings is None:
            return

        if user_edit or (self.step_captures and self.step_settings is None):
            self._store_camera_settings()

            return

        camera_changed = self.camera_settings["camera"] != previous_camera

        if camera_changed and self.step_captures and self.step_settings is not None:
            self._synced = None
            self._apply_step_settings()

    # ------------------------------------------------------------------ #
    # Sync                                                                 #
    # ------------------------------------------------------------------ #

    def _store_camera_settings(self):
        """Write the camera's setup into the selected steps (see the module
        docstring); a source that is no QCamera has no setup to store."""
        settings = self.camera_settings

        if not settings or settings["resolution"] is None:
            return

        for step_id in self.selected_step_ids:
            current = step_id == self.step_id

            if current and not self.step_captures:
                continue

            protocol_tree_set_cell_publisher.publish(
                step_id=step_id,
                col_id=CAPTURE_CAMERA_SETTINGS_FIELD_ID,
                value=settings,
                only_if_set=not current,
            )

        if self.step_captures:
            self.step_settings = settings
            self._synced = (self.step_id, settings)

    def _apply_step_settings(self):
        """Ask the device viewer to apply the current step's setup, unless it
        is the one last synced with the camera."""
        settings = normalize_camera_settings(self.step_settings)

        if settings is None or self._synced == (self.step_id, settings):
            return

        self._synced = (self.step_id, settings)

        camera_apply_settings_publisher.publish(
            {
                **settings,
                "request_id": uuid.uuid4().hex,
                "context": f"Step {self.step_label}",
            }
        )


def _step_label(cells):
    """'1.2 · Wash' from the tree's id (0-indexed path) and name cells."""
    path = cells.get("id") or []
    number = ".".join(str(index + 1) for index in path)
    name = cells.get("name") or ""

    return " · ".join(part for part in (number, name) if part)
