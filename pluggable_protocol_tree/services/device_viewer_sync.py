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

The worker-thread dramatiq listener sets per-topic trait Events; @observe
handlers consume them (dispatch="ui" for the ones that mutate rows, so
cell_changed -> QtTreeModel.dataChanged runs on the GUI thread). This replaces
the former Qt QObject signal bridge.
"""

from __future__ import annotations

from collections import defaultdict

import dramatiq

from pyface.qt.QtCore import QObject
from pyface.qt.QtWidgets import QWidget

from traits.api import Bool, Dict, HasTraits, Instance, Str, Property, List, observe, Set, Int, Event

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
from dropbot_controller.consts import REALTIME_MODE_UPDATED, DROPBOT_DISCONNECTED
from electrode_controller.consts import electrode_state_change_publisher
from logger.logger_service import get_logger
from microdrop_utils.dramatiq_controller_base import (
    generate_class_method_dramatiq_listener_actor,
)
from microdrop_application.consts import ADVANCED_MODE_CHANGE
from microdrop_application.dialogs.pyface_wrapper import confirm, YES
from microdrop_application.menus import is_advanced_mode
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from pluggable_protocol_tree.consts import (
    DV_EXECUTION_PARAM_COL_IDS, ELECTRODE_TO_CHANNEL_KEY,
    PROTOCOL_TREE_ADD_STEP, PROTOCOL_TREE_DISPLAY_STATE,
    PROTOCOL_TREE_SET_CELL, SYNC_LISTENER_NAME,
    protocol_tree_row_selected_publisher,
)
from pluggable_protocol_tree.models.cell_sync import (
    ProtocolTreeAddStepMessage, ProtocolTreeSetCellMessage,
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


def _insert_step_from_message(row_manager, msg) -> None:
    """Insert the step a PROTOCOL_TREE_ADD_STEP message describes.

    Placement: after the step ``after_step_id``; as the last child of
    the group ``group_id``; appended at the root when neither resolves.
    ``cells`` values arrive in each column's serialized form and are
    deserialized through the live column set — unknown col_ids are
    skipped (plugin not loaded), matching persistence's behavior.
    """
    values = {}
    by_id = {c.model.col_id: c for c in row_manager.columns}
    for col_id, raw in (msg.cells or {}).items():
        col = by_id.get(col_id)
        if col is None:
            logger.warning(f"add_step: skipping unknown column {col_id!r}")
            continue
        values[col_id] = col.model.deserialize(raw)
    if msg.name:
        values["name"] = msg.name

    parent_path, index = (), None
    if msg.after_step_id:
        row = row_manager.get_row_by_uuid(msg.after_step_id)
        if row is not None and not isinstance(row, GroupRow):
            path = tuple(row.path)
            parent_path, index = path[:-1], path[-1] + 1
    elif msg.group_id:
        group = row_manager.get_row_by_uuid(msg.group_id)
        if isinstance(group, GroupRow):
            parent_path = tuple(group.path)
    new_path = row_manager.add_step(
        parent_path=parent_path, index=index, values=values,
    )

    # add_step writes cell values via bare setattr, bypassing set_value and
    # the on_row_loaded column hook. Runtime-derived column state (issue
    # #541 locks and the like) must be rebuilt now that every cell value is
    # in place — mirrors persistence.py's post-load hook pass.
    new_row = row_manager.get_row(new_path)
    for col in row_manager.columns:
        hook = getattr(col.model, "on_row_loaded", None)
        if hook is not None:
            hook(new_row)


class DeviceViewerSyncController(HasTraits):
    row_manager              = Instance(RowManager)
    parent_widget            = Instance(QWidget, allow_none=True)
    dramatiq_actor           = Instance(dramatiq.Actor, allow_none=True)
    listener_name            = Str(SYNC_LISTENER_NAME)

    _free_mode_stash         = Instance(dict, allow_none=True)
    free_mode                = Bool(False)
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
    # editability in step with a mid-run toggle (#434). Seeded from the
    # persisted value: the topic only fires on a toggle, so a session that
    # starts with Advanced Mode already on must not read a stale False.
    advanced_mode = Bool()

    # Events fired by the worker-thread dramatiq listener; observed below so
    # the per-topic work runs on a trait notification instead of a Qt signal
    # bridge. The row-mutating ones use dispatch="ui" to marshal onto the GUI
    # thread (cell_changed -> QtTreeModel.dataChanged must run there); the
    # Qt-free ones (geometry, realtime, advanced mode) run inline.
    _geometry_changed_event       = Event(Str)
    _dv_state_changed_event       = Event(Str)
    _protocol_running_changed_event = Event(Bool)
    _step_params_committed_event  = Event(Str)
    _set_cell_request_event       = Event(Str)
    _add_step_request_event       = Event(Str)

    def _advanced_mode_default(self):
        return bool(is_advanced_mode())

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
        """Bind the controller to a ProtocolTreeWidget instance.

        The dramatiq-topic handlers are wired declaratively via @observe on the
        trait Events below (no Qt signal bridge); only the tree's own selection
        signal is connected here."""
        self._tree_widget = tree_widget
        selection_model = tree_widget.tree.selectionModel()
        selection_model.currentChanged.connect(self._on_current_changed)
        self._selection_model = selection_model

    def detach(self) -> None:
        """Disconnect the tree selection signal. The @observe handlers tear
        down with the controller; dramatiq broker shutdown handles the actor."""
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
    def _update_metadata(self, event=None):
        logger.info(f"PROTOCOL TREE (Device Sync): Updating metadata. Electrode Channels Change: {event.new}")
        self.row_manager.protocol_metadata[ELECTRODE_TO_CHANNEL_KEY] = event.new

    @observe("row_manager:cell_changed")
    def _republish_on_param_cell_change(self, event):
        """Cell edits on the selected step rebroadcast row_selected so
        column-owning panes tracking the selection stay current (e.g. the
        fluorescence cell checked/unchecked mid-selection). Edits to an
        execution-param cell additionally republish display state so the
        DV sidebar reloads + rebaselines - protocol values supersede
        whatever the sidebar holds. DV-originated writes (the commit
        handler) suppress this and publish once at the end instead."""
        if self._suppress_publish or not self._last_selected_uuid:
            return
        try:
            row = self.row_manager.get_row(tuple(event.new["path"]))
        except (IndexError, AttributeError):
            return
        if isinstance(row, GroupRow) or row.uuid != self._last_selected_uuid:
            return
        self._publish_row_selected(row)
        if event.new.get("col_id") not in DV_EXECUTION_PARAM_COL_IDS:
            return
        if self._free_mode_stash is not None:
            # Never let a cell edit trigger the leave-free-mode prompt
            # inside _publish_for_row; the next selection change handles it.
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
    @observe("free_mode")
    def _cannot_publish_actuation_log(self, event):
        reason = ""
        if self._protocol_running:
            reason += "Protocol running; "

        if not self.realtime_mode:
            reason += "Realtime mode off; "

        if self.free_mode:
            reason += "In Free-mode"

        if reason:
            logger.warning(f"PROTOCOL TREE (Device Sync): Cannot publish actuations; reason: {reason}")
        else:
            logger.info("PROTOCOL TREE (Device Sync): Will publish actuations")

    @observe("actuated_channels")
    def _send_actuation_request(self, event):
        if not self._protocol_running and self.realtime_mode and not self._free_mode_stash:
            logger.info(f"PROTOCOL TREE (Device Sync): Publishing electrode actuation:{self.actuated_channels}")
            electrode_state_change_publisher.publish(actuated_channels=self.actuated_channels)

    @observe("realtime_mode")
    def _realtime_mode_change(self, event):
        if self._protocol_running or not self.realtime_mode:
            return

        if self._free_mode_stash:
            logger.debug("Not processing actuation request... In free mode.")
            return

        logger.info(f"PROTOCOL TREE (Device Sync): Publishing electrode actuation:{self.actuated_channels}")
        electrode_state_change_publisher.publish(actuated_channels=self.actuated_channels)

    # --- worker-thread dispatch (no Qt / RowManager mutation here) -----

    def _listener_routine(self, message: str, topic: str) -> None:
        logger.debug(f"PROTOCOL TREE (Device Sync): Topic = {topic}; Message = {message}")
        if topic == DEVICE_VIEWER_STATE_CHANGED:
            self._dv_state_changed_event = message
        elif topic == DEVICE_VIEWER_GEOMETRY_CHANGED:
            self._geometry_changed_event = message
        elif topic == PROTOCOL_RUNNING:
            self._protocol_running_changed_event = (message.casefold() == "true")
        elif topic == STEP_PARAMS_COMMIT:
            self._step_params_committed_event = message
        elif topic == PROTOCOL_TREE_SET_CELL:
            self._set_cell_request_event = message
        elif topic == PROTOCOL_TREE_ADD_STEP:
            self._add_step_request_event = message
        elif topic == REALTIME_MODE_UPDATED:
            self.realtime_mode = (message.casefold() == "true")
        elif topic == DROPBOT_DISCONNECTED:
            self.realtime_mode = False
        elif topic == ADVANCED_MODE_CHANGE:
            # Qt-free trait — the dock pane's dispatch="ui" observer marshals
            # the GUI-thread work (tree editability, live ctx update).
            self.advanced_mode = (message.casefold() == "true")

    # --- Qt-thread / trait Event handlers / observers --------------------------------------------

    @observe("_geometry_changed_event")
    def _on_geometry_changed(self, event) -> None:
        """Receive DEVICE_VIEWER_GEOMETRY_CHANGED on the Qt thread."""
        payload = event.new
        try:
            geo_change_msg = GeometryChangedMessage.deserialize(payload)
        except Exception as e:
            logger.warning(f"failed to parse geometry payload {payload!r}: {e}")
            return

        logger.info("Device View Sync: Received geometry change")
        self.electrode_ids_channels_map = dict(geo_change_msg.id_to_channel)

    @observe("_dv_state_changed_event", dispatch="ui")
    def _on_dv_state(self, event) -> None:
        """DEVICE_VIEWER_STATE_CHANGED. dispatch="ui" so it runs on the GUI
        thread: the step-scoped branch mutates rows, and row cell_changed ->
        QtTreeModel.dataChanged must fire there. Captures free-mode toggles
        into _free_mode_stash; clears stash for any step-scoped/empty message."""
        payload = event.new
        try:
            dv_msg = DeviceViewerMessageModel.deserialize(payload)
            logger.info(f"PROTOCOL TREE (Device Sync): received message: {dv_msg}")
        except Exception as e:
            logger.warning(f"failed to parse DV state: {e}")
            return

        # The electrode->channel mapping is no longer carried on state messages
        # (PPT-9 / #415): it arrives once, change-gated, on
        # DEVICE_VIEWER_GEOMETRY_CHANGED (handled in _on_geometry_changed) and
        # is the authoritative source for the metadata. The DV always publishes
        # geometry on init, so no cold-start seed from state messages is needed.
        electrodes = set()
        for ch in dv_msg.channels_activated:
            if ch in self.channels_electrode_ids_map:
                electrodes.update(self.channels_electrode_ids_map[ch])

        routes = [list(ids) for ids, _color in dv_msg.routes]

        if dv_msg.step_id:
            self.free_mode = False
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

            # During a run (Advanced Mode keeps the viewer editable, #434) the
            # viewer only shows the CURRENT PHASE's electrodes, which for a
            # route/multi-phase step is a subset of the step's full set.
            # Writing that subset back would clobber the rest of the step, so
            # restrict the live write-back to routeless (static) steps, where
            # the actuated set IS the whole step. Editing geometry/routes of a
            # route step is an idle-only operation.
            if self._protocol_running and (row.routes or routes):
                logger.info(
                    f"Skipping live electrode write-back for route step "
                    f"{dv_msg.step_id} during a run; actuation reflected to "
                    f"hardware only."
                )
                return

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

        self.free_mode = True

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

    @observe("_step_params_committed_event", dispatch="ui")
    def _on_step_params_commit(self, event) -> None:
        """STEP_PARAMS_COMMIT: the DV sidebar's route-executor params pushed
        onto the step that owns them (the DV commit button, or the commit
        choice of its step-transition prompt). dispatch="ui" — it mutates rows
        (cell_changed -> QtTreeModel.dataChanged on the GUI thread)."""
        payload = event.new
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

    @observe("_set_cell_request_event", dispatch="ui")
    def _on_set_cell_request(self, event) -> None:
        """PROTOCOL_TREE_SET_CELL: a column-owning pane writes one value
        into the step that owns it (e.g. the fluorescence pane's
        live-tracking write-back). dispatch="ui" — it mutates rows.
        Ignored during a run: the executor owns the rows then, and pane
        edits are display-only."""
        try:
            set_cell_msg = ProtocolTreeSetCellMessage.deserialize(event.new)
        except Exception as e:
            logger.warning(f"failed to parse set-cell request: {e}")
            return
        if self._protocol_running:
            logger.info(
                f"set-cell for {set_cell_msg.col_id!r} ignored during a run")
            return
        row = self.row_manager.get_row_by_uuid(set_cell_msg.step_id)
        if row is None or isinstance(row, GroupRow):
            logger.warning(
                f"set-cell for unknown step {set_cell_msg.step_id!r} dropped")
            return
        try:
            column = self.row_manager._column_by_id(set_cell_msg.col_id)
        except KeyError:
            logger.warning(
                f"set-cell for unknown column {set_cell_msg.col_id!r} dropped")
            return
        value = column.model.deserialize(set_cell_msg.value)
        current = column.model.get_value(row)
        if set_cell_msg.only_if_set and current is None:
            return
        if current == value:
            return
        # set_value fires cell_changed, so the edit flows through the same
        # dirty tracking + rebroadcast path as a manual cell edit.
        self.row_manager.set_value(tuple(row.path), set_cell_msg.col_id, value)
        logger.info(f"set-cell applied to Step {row.dotted_path()} "
                    f"column {set_cell_msg.col_id!r}")

    @observe("_add_step_request_event", dispatch="ui")
    def _on_add_step_request(self, event) -> None:
        """PROTOCOL_TREE_ADD_STEP: insert a plugin-authored step. Runs on
        the GUI thread (row mutation); refused mid-run like set_cell."""
        if self._protocol_running:
            logger.warning("add_step request ignored: protocol running")
            return
        try:
            msg = ProtocolTreeAddStepMessage.deserialize(event.new)
        except Exception as e:
            logger.warning(f"bad add_step payload {event.new!r}: {e}")
            return
        self._suppress_publish = True
        try:
            _insert_step_from_message(self.row_manager, msg)
        finally:
            self._suppress_publish = False

    def _publish_row_selected(self, row) -> None:
        """Broadcast PROTOCOL_TREE_ROW_SELECTED: the selected step's uuid
        plus every column's serialized value (step_id None for free mode /
        group selection). Column-owning panes (fluorescence) live-track
        the selected step through this without reaching into the tree."""
        if row is None:
            protocol_tree_row_selected_publisher.publish(step_id=None,
                                                         cells={})
            return
        if isinstance(row, GroupRow):
            protocol_tree_row_selected_publisher.publish(
                step_id=None, group_id=row.uuid, cells={})
            return
        cells = {
            column.model.col_id:
                column.model.serialize(column.model.get_value(row))
            for column in self.row_manager.columns
        }
        protocol_tree_row_selected_publisher.publish(step_id=row.uuid,
                                                     cells=cells)

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

        # While a protocol is running (incl. paused), selection-driven
        # publishes still fire so the DV follows the executor/nav — but they
        # must NOT hand the operator an editable viewer unless Advanced Mode is
        # on (#434). Without this, selecting a step mid-run unlocked electrode
        # actuation and route drawing. Idle: always editable.
        editable = (not self._protocol_running) or bool(self.advanced_mode)

        prev_uuid = self._last_selected_uuid
        if row is None or isinstance(row, GroupRow):
            self.actuated_channels = set()
            msg = ProtocolTreeDisplayMessage(free_mode=True, editable=editable)
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
                editable=editable,
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
        self._publish_row_selected(row)

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

    @observe("_protocol_running_changed_event", dispatch="ui")
    def _on_protocol_running(self, event) -> None:
        # dispatch="ui" keeps this serialized on the GUI thread with the
        # row-mutating handlers that read _protocol_running (matches the prior
        # single-bridge ordering).
        self._protocol_running = bool(event.new)

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
