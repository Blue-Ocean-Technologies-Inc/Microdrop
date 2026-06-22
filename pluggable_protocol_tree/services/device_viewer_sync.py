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

from collections import defaultdict

import dramatiq

from pyface.qt.QtCore import QObject, Signal
from pyface.qt.QtWidgets import QWidget

from traits.api import Bool, Dict, HasTraits, Instance, Str, Property, List, observe, Set, Int

from device_viewer.consts import (
    DEVICE_VIEWER_GEOMETRY_CHANGED,
    DEVICE_VIEWER_STATE_CHANGED,
    PROTOCOL_RUNNING,
    STEP_PARAMS_COMMIT,
)
from device_viewer.models.messages import (
    DeviceViewerMessageModel, GeometryChangedMessage,
)
from device_viewer.models.step_params_commit import StepParamsCommitMessage
from dropbot_controller.consts import REALTIME_MODE_UPDATED
from electrode_controller.consts import electrode_state_change_publisher
from logger.logger_service import get_logger
from microdrop_utils.dramatiq_controller_base import (
    generate_class_method_dramatiq_listener_actor,
)
from microdrop_application.consts import ADVANCED_MODE_CHANGE
from microdrop_application.dialogs.pyface_wrapper import confirm, YES
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from pluggable_protocol_tree.consts import (
    DV_EXECUTION_PARAM_COL_IDS, ELECTRODE_TO_CHANNEL_KEY,
    PROTOCOL_TREE_DISPLAY_STATE, SYNC_LISTENER_NAME,
)
from pluggable_protocol_tree.models.display_state import (
    ProtocolTreeDisplayMessage,
)
from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget

logger = get_logger(__name__)


def _execution_params_for_row(row) -> dict:
    """The row's route-execution params keyed/typed per the DV sidebar
    contract (ProtocolTreeDisplayMessage.execution_params /
    StepParamsCommitMessage): the DV's ``repetitions`` is the tree's
    ``route_repetitions`` column, ``soft_terminate`` is ``soft_end``,
    and its ``repeat_duration`` spinner is integer-granular."""

    ## The device viewer only has spinners to set the repeats num or repeat duration.
    ## It does not have dialogs to change controls, simply indicates by resetting repeat duration to 0 if
    ## repeat num in control, and repeat num to 1 and repeat duration to some number when duration based repeats.
    if row.repeat_duration_controls:
        repeat_duration = row.repeat_duration
        route_repetitions = 1

    else:
        repeat_duration = 0.0
        route_repetitions = row.route_repetitions

    return {
        "duration": float(getattr(row, "duration_s", 1.0) or 0.0),
        "repetitions": int(route_repetitions),
        "repeat_duration": int(round(float(repeat_duration))),
        "trail_length": int(getattr(row, "trail_length", 1) or 1),
        "trail_overlay": int(getattr(row, "trail_overlay", 0) or 0),
        "soft_start": bool(getattr(row, "soft_start", False)),
        "soft_terminate": bool(getattr(row, "soft_end", False)),
        "linear_repeats": bool(getattr(row, "linear_repeats", False)),
    }


def _col_values_from_execution_params(params: dict) -> dict:
    """Inverse of _execution_params_for_row: DV sidebar contract keys ->
    tree column ids/types, ready for setattr onto a row."""

    # Of the Route Reps <-> Route Reps Dur pair, only the row's
    # controlling knob is written — the pane's reconciliation pass
    # recalculates the derived one, exactly as for a manual cell
    # edit. The pop/reassign moves the controlling knob to the end
    # of the write order so its reconcile sees the other committed
    # values already in place.

    result = {
        "duration_s": float(params["duration"]),
        "route_repetitions": int(params["repetitions"]),
        "repeat_duration": float(params["repeat_duration"]),
        "trail_length": int(params["trail_length"]),
        "trail_overlay": int(params["trail_overlay"]),
        "soft_start": bool(params["soft_start"]),
        "soft_end": bool(params["soft_terminate"]),
        "linear_repeats": bool(params["linear_repeats"]),
    }

    result["repeat_duration_controls"] = bool(float(result["repeat_duration"]))

    if result["repeat_duration_controls"]:
        del result["route_repetitions"]
        result["repeat_duration"] = result.pop("repeat_duration")
    else:
        del result["repeat_duration"]
        result["route_repetitions"] = result.pop("route_repetitions")


    return result


class _Bridge(QObject):
    """Qt signal bridge - Dramatiq actor runs on a worker thread, Qt
    mutations must happen on the GUI thread."""

    dv_state_received        = Signal(str)
    geometry_changed         = Signal(str)
    protocol_running_changed = Signal(bool)
    step_params_committed    = Signal(str)


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

    #: Map of the unique channels found amongst the electrodes, and various electrode ids associated with them
    # Note that channel-electrode_id is one-to-many! So there is meaningful difference in acting on one or the other
    electrode_ids_channels_map = Dict(Str, Int)
    channels_electrode_ids_map = Property(Dict(Int, List(Str)), observe='electrode_ids_channels_map')

    _tree_widget             = Instance(ProtocolTreeWidget, allow_none=True)
    _selection_model         = Instance(QObject, allow_none=True)

    realtime_mode = Bool()
    actuated_channels = Set(Int)
    # Mirror of the operator's Advanced Mode toggle (ADVANCED_MODE_CHANGE).
    # The dock pane observes this to keep the live run's context + the tree's
    # editability in step with a mid-run toggle (#434).
    advanced_mode = Bool(False)

    def _bridge_default(self) -> _Bridge:
        return _Bridge()

    def traits_init(self):
        logger.info(f"Starting Protocol Tree Device View Sync Controller listener")
        self.dramatiq_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self._listener_routine,
        )

        # seed electrode_ids_channels_map from metadata if it exists
        if self.row_manager.protocol_metadata.get(ELECTRODE_TO_CHANNEL_KEY):
            self.electrode_ids_channels_map = (
                self.row_manager.protocol_metadata[ELECTRODE_TO_CHANNEL_KEY]
            )

    # --- public lifecycle ----------------------------------------------

    def attach(self, tree_widget) -> None:
        """Bind the controller to a ProtocolTreeWidget instance."""
        self._tree_widget = tree_widget
        self.bridge.geometry_changed.connect(self._on_geometry_qt)
        self.bridge.dv_state_received.connect(self._on_dv_state_qt)
        self.bridge.protocol_running_changed.connect(self._on_protocol_running_qt)
        self.bridge.step_params_committed.connect(self._on_step_params_commit_qt)
        selection_model = tree_widget.tree.selectionModel()
        selection_model.currentChanged.connect(self._on_current_changed)
        self._selection_model = selection_model

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
        try:
            self.bridge.protocol_running_changed.disconnect(
                self._on_protocol_running_qt,
            )
        except (RuntimeError, TypeError):
            pass
        try:
            self.bridge.step_params_committed.disconnect(
                self._on_step_params_commit_qt,
            )
        except (RuntimeError, TypeError):
            pass
        try:
            if self._selection_model is not None:
                self._selection_model.currentChanged.disconnect(
                    self._on_current_changed,
                )
        except (RuntimeError, TypeError):
            pass
        self._selection_model = None
        self._tree_widget = None

    # -------- trait observers --------------
    @observe("electrode_ids_channels_map")
    def _update_metadata(self, event):
        self.row_manager.protocol_metadata[ELECTRODE_TO_CHANNEL_KEY] = event.new

    @observe("row_manager:cell_changed")
    def _republish_on_param_cell_change(self, event):
        """Tree-originated edits to an execution-param cell on the selected
        step republish display state so the DV sidebar reloads + rebaselines
        - protocol values supersede whatever the sidebar holds. DV-originated
        writes (the commit handler) suppress this and publish once at the
        end instead."""
        if event.new.get("col_id") not in DV_EXECUTION_PARAM_COL_IDS:
            return
        if self._suppress_publish or not self._last_selected_uuid:
            return
        if self._free_mode_stash is not None:
            # Never let a cell edit trigger the leave-free-mode prompt
            # inside _publish_for_row; the next selection change handles it.
            return
        try:
            row = self.row_manager.get_row(tuple(event.new["path"]))
        except (IndexError, AttributeError):
            return
        if isinstance(row, GroupRow) or row.uuid != self._last_selected_uuid:
            return
        self._publish_for_row(row)

    def _get_channels_electrode_ids_map(self):
        """
        Creates an inverted map from each channel to a list of its electrode IDs.
        This property depends on and reuses the result from the first property.
        """

        channel_to_electrode_ids_map = defaultdict(list)

        if self.electrode_ids_channels_map:
            for electrode_id, channel in self.electrode_ids_channels_map.items():
                channel_to_electrode_ids_map[channel].append(electrode_id)

        return channel_to_electrode_ids_map

    @observe("_protocol_running")
    @observe("realtime_mode")
    def _cannot_publish_actuation_log(self, event):
        reason = ""
        if self._protocol_running:
            reason += "Protocol running; "

        if self.realtime_mode:
            reason += "Realtime mode"

        if reason:
            logger.warning(f"PROTOCOL TREE: Cannot publish actuations; reason: {reason}")
        else:
            logger.info("PROTOCOL TREE: Can publish actuations when step selected")


    @observe("realtime_mode")
    @observe("actuated_channels")
    def _send_actuation_request(self, event):
        if self._protocol_running or not self.realtime_mode:
            return

        logger.info(f"PROTOCOL TREE: Publishing electrode actuation:{self.actuated_channels}")
        electrode_state_change_publisher.publish(actuated_channels=self.actuated_channels)

    # --- worker-thread dispatch (no Qt / RowManager mutation here) -----

    def _listener_routine(self, message: str, topic: str) -> None:
        if topic == DEVICE_VIEWER_STATE_CHANGED:
            self.bridge.dv_state_received.emit(message)
        elif topic == DEVICE_VIEWER_GEOMETRY_CHANGED:
            self.bridge.geometry_changed.emit(message)
        elif topic == PROTOCOL_RUNNING:
            self.bridge.protocol_running_changed.emit(message.casefold() == "true")
        elif topic == STEP_PARAMS_COMMIT:
            self.bridge.step_params_committed.emit(message)
        elif topic == REALTIME_MODE_UPDATED:
            self.realtime_mode = True
        elif topic == ADVANCED_MODE_CHANGE:
            # Qt-free trait — the dock pane's dispatch="ui" observer marshals
            # the GUI-thread work (tree editability, live ctx update).
            self.advanced_mode = (message.casefold() == "true")

    # --- Qt-thread handlers --------------------------------------------

    def _on_geometry_qt(self, payload: str) -> None:
        """Receive DEVICE_VIEWER_GEOMETRY_CHANGED on the Qt thread."""
        try:
            geo_change_msg = GeometryChangedMessage.deserialize(payload)
        except Exception as e:
            logger.warning(f"failed to parse geometry payload {payload!r}: {e}")
            return
        self.electrode_ids_channels_map = dict(geo_change_msg.id_to_channel)

    def _on_dv_state_qt(self, payload: str) -> None:
        """Receive DEVICE_VIEWER_STATE_CHANGED on the Qt thread. Captures
        free-mode toggles into _free_mode_stash; clears stash for any
        step-scoped or empty message."""
        try:
            dv_msg = DeviceViewerMessageModel.deserialize(payload)
            logger.info(f"Protocol Tree: Device View Sync recieved message: {dv_msg}")
        except Exception as e:
            logger.warning(f"failed to parse DV state: {e}")
            return

        # Cold-start seed: populate metadata if empty so reverse-lookup
        # works. Non-empty metadata comes from GEOMETRY_CHANGED, which
        # is authoritative; state msgs only fill the gap at cold-start.
        if (not self.row_manager.protocol_metadata.get(ELECTRODE_TO_CHANNEL_KEY)
                and dv_msg.id_to_channel):

            logger.info(f"Protocol Tree: Applying initial id_to_channel to metadata:  {dv_msg.id_to_channel} ")
            self.electrode_ids_channels_map = dict(dv_msg.id_to_channel)

        electrodes = set()
        for ch in dv_msg.channels_activated:
            if ch in self.channels_electrode_ids_map:
                electrodes.update(self.channels_electrode_ids_map[ch])

        routes = [list(ids) for ids, _color in dv_msg.routes]

        if dv_msg.step_id:
            # Step-scoped edit: write electrodes/routes back to the
            # matching row's columns. Mirrors the legacy protocol_grid
            # 'edit step electrodes via DV' behavior.
            self._free_mode_stash = None
            row = self.row_manager.get_row_by_uuid(dv_msg.step_id)
            if row is None or isinstance(row, GroupRow):
                return
            path = tuple(row.path)

            # trigger actuations if possible
            self.actuated_channels = set(dv_msg.channels_activated)

            # Direct trait writes bypass both QtTreeModel.setData and
            # the delegate, so fire cell_changed for each column the
            # user actually changed — the protocol state tracker uses
            # this for O(1) incremental dirty bookkeeping.
            if list(row.electrodes or []) != electrodes:
                row.electrodes = list(electrodes)
                self.row_manager.cell_changed = {
                    "path": path, "col_id": "electrodes",
                }
            if list(row.routes or []) != routes:
                row.routes = routes
                self.row_manager.cell_changed = {
                    "path": path, "col_id": "routes",
                }
            return

        if not electrodes and not routes:
            self._free_mode_stash = None
            return

        # Free-mode state messages also carry the sidebar's current
        # execution params (None otherwise) so an 'Insert as New Step'
        # seeds them into the new row.
        self._free_mode_stash = {
            "electrodes": electrodes,
            "routes": routes,
            "execution_params": dv_msg.execution_params,
        }

    def _on_step_params_commit_qt(self, payload: str) -> None:
        """Receive STEP_PARAMS_COMMIT on the Qt thread: the DV sidebar's
        route-executor params pushed onto the step that owns them (the
        DV commit button, or the commit choice of its step-transition
        prompt)."""
        try:
            commit_msg = StepParamsCommitMessage.deserialize(payload)
        except Exception as e:
            logger.warning(f"failed to parse step-params commit: {e}")
            return
        row = self.row_manager.get_row_by_uuid(commit_msg.step_id)
        if row is None or isinstance(row, GroupRow):
            logger.warning(
                f"step-params commit for unknown step "
                f"{commit_msg.step_id!r} dropped"
            )
            return
        path = tuple(row.path)

        new_values = _col_values_from_execution_params(commit_msg.model_dump(exclude={"step_id"}))
        # Direct trait writes bypass QtTreeModel.setData and the delegate,
        # so fire cell_changed per changed column — it drives both the
        # dirty tracker and the pane's repeat-duration reconciliation.
        # Publishing is suppressed for the duration: these cell changes
        # are DV-originated, so the per-cell republish observer must not
        # echo intermediate states — one publish at the end instead.
        self._suppress_publish = True
        try:
            for col_id, value in new_values.items():
                if getattr(row, col_id, None) == value:
                    continue
                setattr(row, col_id, value)
                self.row_manager.cell_changed = {"path": path, "col_id": col_id}
        finally:
            self._suppress_publish = False

        logger.info(f"DV step-params commit applied to Step {row.dotted_path()}")
        # Echo the final (post-reconciliation) state back so the DV
        # rebaselines its commit button on what the tree actually stored.
        if row.uuid == self._last_selected_uuid:
            self._publish_for_row(row)

    def _publish_for_row(self, row) -> None:
        """Publish PROTOCOL_TREE_DISPLAY_STATE for the given row (or
        free-mode payload if row is None / a group). Gated only on the
        suppress flag — selection-driven publishes happen during a run
        too (executor advances + nav buttons + user clicks all push the
        DV to the right step display)."""
        if self._suppress_publish:
            return

        # Resolve the unsaved free-mode stash on any selection change
        # (step, group, or deselect) — spec §4.D requires the prompt
        # to fire whenever we leave free mode.
        if self._free_mode_stash is not None:
            choice = confirm(
                self.parent_widget,
                "You have unsaved changes from free mode.",
                title="Unsaved Free Mode Changes",
                informative=(
                    "There are electrode actuations or routes from free "
                    "mode that have not been saved to a protocol step."
                    "<br><br>Would you like to insert them as a new step?"
                ),
                yes_label="Insert as New Step",
                no_label="Discard Changes",
            )
            if choice == YES:
                self._insert_free_mode_as_new_step()
            self._free_mode_stash = None

        prev_uuid = self._last_selected_uuid
        if row is None or isinstance(row, GroupRow):
            self.actuated_channels = set()
            msg = ProtocolTreeDisplayMessage(free_mode=True)
            self._last_selected_uuid = ""
            if prev_uuid:
                logger.info("DV display --> free mode")
        else:
            # 1-indexed dotted-path id (matches the ID column display)
            # so the DV's status bar shows e.g. "Editing: Step 1.2"
            # rather than the bare row name (which defaults to "Step").
            dotted_id = row.dotted_path()
            msg = ProtocolTreeDisplayMessage(
                electrodes=list(row.electrodes or []),
                routes=list(row.routes or []),
                step_id=row.uuid,
                step_label=f"Step {dotted_id}",
                free_mode=False,
                editable=True,
                execution_params=_execution_params_for_row(row),
            )
            if row.uuid != prev_uuid:
                logger.info(
                    f"DV display  Step {dotted_id} {row.name!r} "
                    f"({len(msg.electrodes)} electrodes, "
                    f"{len(msg.routes)} routes)"
                )
                self.actuated_channels = set(self.electrode_ids_channels_map[id] for id in row.electrodes)

            self._last_selected_uuid = row.uuid
        publish_message(
            topic=PROTOCOL_TREE_DISPLAY_STATE,
            message=msg.serialize(),
        )

    def _insert_free_mode_as_new_step(self) -> None:
        """Reentrancy-guarded RowManager.add_step for the free-mode capture.
        Sets _suppress_publish around the mutation so the model-change
        cascade (which can fire selectionModel.currentChanged) does not
        trigger a duplicate publish from this same click."""
        stash = self._free_mode_stash
        if stash is None:
            return
        values = {
            "name": "Step (free-mode capture)",
            "electrodes": list(stash["electrodes"]),
            "routes": stash["routes"],
        }
        # Seed the sidebar's execution params into the new step (legacy
        # protocol_grid parity) — the DV carries them on free-mode state
        # messages for exactly this purpose.
        if stash.get("execution_params"):
            values.update(
                _col_values_from_execution_params(stash["execution_params"])
            )
        self._suppress_publish = True
        try:
            self.row_manager.add_step(parent_path=(), index=None, values=values)
        finally:
            self._suppress_publish = False

    def _on_protocol_running_qt(self, running: bool) -> None:
        self._protocol_running = bool(running)

    def _on_current_changed(self, current, _previous) -> None:
        """Qt slot wired to selectionModel().currentChanged. Resolves the
        QModelIndex to a row, then delegates to _publish_for_row."""
        if self._suppress_publish:
            return
        # Race guard: signal can fire after detach() clears _tree_widget.
        if self._tree_widget is None:
            return
        if not current.isValid():
            self._publish_for_row(None)
            return
        path = self._tree_widget.index_to_path(current)
        try:
            row = self.row_manager.get_row(path)
        except IndexError:
            self._publish_for_row(None)
            return
        self._publish_for_row(row)
