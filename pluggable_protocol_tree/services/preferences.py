"""Protocol preferences model + Settings-dialog pane.

Ported from ``protocol_grid.preferences`` (#419 / PPT-14.1).
``preferences_path`` ("microdrop.protocol") and every field name are kept
identical to the legacy model so persisted user settings carry over. The
legacy plugin keeps its own untouched copy — both plugins are standalone
until PPT-9 deletes protocol_grid.
"""

from pathlib import Path

# Enthought library imports.
from envisage.ui.tasks.api import PreferencesCategory, PreferencesPane
from apptools.preferences.api import PreferencesHelper
from traits.api import Bool, Dict, Directory, Enum, Float, Str
from traits.etsconfig.api import ETSConfig
from traitsui.api import Group, View, Item

from microdrop_style.text_styles import preferences_group_style_sheet
from microdrop_utils.preferences_UI_helpers import create_grid_group
from microdrop_utils.traitsui_qt_helpers import (
    DictFloatTableEditor, RangeWithViewHints,
)

from ..consts import ACK_TIMEOUT_MAX_S, ACK_TIMEOUT_MIN_S, ACK_WAIT_FOREVER, CAMERA_PREWARM_MAX_S, CAMERA_PREWARM_MIN_S, \
    DEFAULT_CAMERA_PREWARM_SECONDS, DEFAULT_LOGS_SETTLING_SECONDS, DEFAULT_REALTIME_SETTLING_SECONDS, \
    PROTOCOL_TREE_PREFERENCES_TAB_ID, SETTLING_TIME_MAX_S, SETTLING_TIME_MIN_S

from logger.logger_service import get_logger
logger = get_logger(__name__)


class StepTime:
    """Values for the capture_time preference. Plain str constants, NOT a
    Python enum — they are persisted and compared as bare strings (e.g.
    capture_column's ``capture_time == StepTime.START``)."""

    END = "Step End"
    START = "Step Start"


class ProtocolPreferences(PreferencesHelper):
    """Protocol-tree preferences helper.

    Distinct from the legacy ``protocol_grid.preferences.
    ProtocolPreferences`` but bound to the same "microdrop.protocol"
    node for settings continuity (see module docstring). In the full app
    the dock pane binds it to the application's preferences via
    ``ProtocolPreferences(preferences=app.preferences)``; constructed
    bare it falls back to the global default node (demos / headless
    tests — see ``ensure``)."""

    #### 'PreferencesHelper' interface ########################################

    # The path to the preference node that contains the preferences.
    preferences_path = "microdrop.protocol"

    #### Preferences ##########################################################
    camera_prewarm_seconds = RangeWithViewHints(
        value=DEFAULT_CAMERA_PREWARM_SECONDS,
        low=CAMERA_PREWARM_MIN_S,
        high=CAMERA_PREWARM_MAX_S,
        desc="Camera switch on lead time"
    )

    realtime_mode_settling_time_s = RangeWithViewHints(
        value=DEFAULT_REALTIME_SETTLING_SECONDS,
        low=SETTLING_TIME_MIN_S,
        high=SETTLING_TIME_MAX_S,
        desc="Time to allow for realtime mode to settle pre protocol start"
    )

    logs_settling_time_s = RangeWithViewHints(
        value=DEFAULT_LOGS_SETTLING_SECONDS,
        low=SETTLING_TIME_MIN_S,
        high=SETTLING_TIME_MAX_S,
        desc="Time to allow logs post protocol end"
    )

    prompt_to_restore_realtime_mode = Bool(True)
    keep_realtime_mode_after_protocol = Bool(True)

    capture_time = Enum(StepTime.START, StepTime.END, value=StepTime.START)

    PROTOCOL_REPO_DIR = Directory()

    # Programmatic preference (no Settings-dialog item, like
    # PROTOCOL_REPO_DIR): {col_id: visible} map persisted by the
    # protocol tree's header right-click menu. Keyed by the per-cell
    # col_id — stable across display renames (col_name keying orphaned
    # saved entries when Routes became "Electrodes") and across column
    # reordering. A column absent from the map falls back to its
    # hidden_by_default flag; legacy col_name-keyed entries are read via
    # a fallback in the tree widget and rewritten on the next toggle.
    protocol_tree_column_visibility = Dict(Str, Bool)

    # {col_id: seconds} acknowledgement-wait time per wait-capable column
    # (issue #427), keyed by the stable col_id (base_id for compounds),
    # NOT the display col_name — the same key handlers resolve at run
    # time. Edited in the pane's Column Ack Wait Times grid; 0 = don't
    # wait, ACK_WAIT_FOREVER = wait forever. The dock pane seeds one
    # entry per assembled column whose handler declares a
    # default_ack_time_s (see seed_ack_times_from_columns) — the plugin
    # provider's value is the default, and user edits persisted on the
    # node are never overwritten.
    protocol_tree_ack_times = Dict(Str, Float)

    # Programmatic companion to protocol_tree_ack_times (no Settings
    # item): {col_id: display col_name} so the ack-wait grid shows
    # "Electrodes" / "Voltage (V)" while staying keyed by the stable
    # col_id. Refreshed on every seed — display names follow provider
    # renames, they are not user edits.
    protocol_tree_column_names = Dict(Str, Str)

    # Persisted snapshot of the plugin providers' default_ack_time_s
    # values ({col_id: seconds}). This is what a Settings-dialog revert
    # restores: reverting resets protocol_tree_ack_times to its default,
    # and the default method below reads this trait. Seeding rewrites it
    # only when the contributed defaults actually differ from what is
    # stored — the boot-time load of saved USER values never touches it
    # (a module-global backup tried this before and got overwritten with
    # the user's values on every launch, making revert a no-op).
    protocol_tree_default_ack_times = Dict(Str, Float)

    def _protocol_tree_ack_times_default(self):
        # Copy: the snapshot must not alias the live trait dict.
        return dict(self.protocol_tree_default_ack_times)

    def _PROTOCOL_REPO_DIR_default(self) -> Path:
        default_dir = Path(ETSConfig.user_data) / "Protocols"

        default_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Default repo directory is: {default_dir}")

        return default_dir


    def seed_ack_times_from_columns(self, columns) -> None:
        """Rebuild ``protocol_tree_ack_times`` from the column list: one
        entry per wait-capable column (handler declares a positive
        ``default_ack_time_s``), keyed by ``column.id`` (the model's
        col_id; base_id for compounds and their expanded field cells).
        A persisted user edit wins over the provider default; entries
        whose key matches no current column are dropped, so the grid
        always mirrors the live column set.
        ``protocol_tree_default_ack_times`` (the revert snapshot) and
        ``protocol_tree_column_names`` (column.id -> display name) are
        rebuilt alongside — provider data, not user edits."""
        default_ack_times = {}
        column_names = {}
        for column in columns:
            default_ack_time_s = float(
                getattr(column.handler, "default_ack_time_s", 0.0) or 0.0)
            if default_ack_time_s <= 0:
                continue
            # Display name for the grid's key column: single columns
            # (incl. compound field cells) carry col_name; an unexpanded
            # compound shows its owner field's label. setdefault: a
            # compound's field cells share one id and arrive owner-first,
            # so the owner's label wins.
            field_specs = getattr(column.model, "field_specs", None)
            column_names.setdefault(column.id, (
                getattr(column.model, "col_name", "")
                or (field_specs()[0].col_name if field_specs else column.id)))
            default_ack_times[column.id] = default_ack_time_s
        ack_times = {
            col_id: self.protocol_tree_ack_times.get(col_id, default_ack_time_s)
            for col_id, default_ack_time_s in default_ack_times.items()
        }
        if default_ack_times != self.protocol_tree_default_ack_times:
            self.protocol_tree_default_ack_times = default_ack_times
        if ack_times != self.protocol_tree_ack_times:
            self.protocol_tree_ack_times = ack_times
        if column_names != self.protocol_tree_column_names:
            self.protocol_tree_column_names = column_names


protocol_tree_tab = PreferencesCategory(
    id=PROTOCOL_TREE_PREFERENCES_TAB_ID,
    name="Protocol Settings",
    after="microdrop.device_viewer.preferences",
    before="microdrop.peripheral_settings"
)


class ProtocolPreferencesPane(PreferencesPane):
    """Settings-dialog pane for ProtocolPreferences, based on enthought
    envisage's preferences pane for the Attractors application."""

    #### 'PreferencesPane' interface ##########################################

    # The factory to use for creating the preferences model object.
    model_factory = ProtocolPreferences

    category = protocol_tree_tab.id

    # Create the grid group for the sidebar items.
    camera_settings_grid = create_grid_group(
        ["camera_prewarm_seconds", "capture_time"],
        label_text = ["Camera On Lead Time (s)", "When to Capture Step Picture?"],
        group_label="Camera Config",
        group_show_border=True,
        group_style_sheet=preferences_group_style_sheet,
    )

    general_protocol_settings_grid = create_grid_group(
        items=["realtime_mode_settling_time_s", "logs_settling_time_s"],
        label_text = ["Realtime Mode Pre-Protocol (s)", "Logs Accepted Post-Protocol (s)"],
        group_label="Protocol Settling Times",
        group_show_border=True,
        group_style_sheet=preferences_group_style_sheet,
    )

    realtime_mode_settings_grid = create_grid_group(
        items=["prompt_to_restore_realtime_mode", "keep_realtime_mode_after_protocol"],
        label_text = ["Prompt to keep Realtime Mode?", "Keep Realtime Mode active?"],
        group_label="Realtime Mode Persistence",
        group_show_border=True,
        group_style_sheet=preferences_group_style_sheet,
    )

    ack_times_grid = Group(
        Item("protocol_tree_ack_times", show_label=False,
             editor=DictFloatTableEditor(
                 key_label="Column", value_label="Wait Time (s)",
                 key_labels_name="protocol_tree_column_names",
                 low=ACK_TIMEOUT_MIN_S, high=ACK_TIMEOUT_MAX_S,
                 decimals=1, step=0.5,
                 allow_infinity=True,
                 infinity_value=ACK_WAIT_FOREVER,
                 infinity_text="∞ (wait forever)",
             )),
        label="Column Ack Wait Times (0 = don't wait)",
        show_border=True,
        style_sheet=preferences_group_style_sheet,
    )

    view = View(
        Item("_"),  # Separator
        general_protocol_settings_grid,
        Item("_"),
        realtime_mode_settings_grid,
        Item("_"),
        camera_settings_grid,
        Item("_"),
        ack_times_grid,
        Item("_"),  # Separator to space this out from further contributions to the pane.
        resizable=True
    )
