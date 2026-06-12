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

from pluggable_protocol_tree.consts import (
    ACK_TIMEOUT_MAX_S,
    ACK_TIMEOUT_MIN_S,
    CAMERA_PREWARM_MAX_S,
    CAMERA_PREWARM_MIN_S,
    DEFAULT_CAMERA_PREWARM_SECONDS,
    DEFAULT_LOGS_SETTLING_SECONDS,
    DEFAULT_REALTIME_SETTLING_SECONDS,
    PROTOCOL_TREE_PREFERENCES_TAB_ID,
    SETTLING_TIME_MAX_S,
    SETTLING_TIME_MIN_S,
)

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
    # PROTOCOL_REPO_DIR): {col_name: visible} map persisted by the
    # protocol tree's header right-click menu. Keyed by col_name (stable
    # display identity), not column index — indices shift when the column
    # set changes. A column absent from the map falls back to its
    # hidden_by_default flag.
    protocol_tree_column_visibility = Dict(Str, Bool)

    # {col_name: seconds} acknowledgement-wait time per wait-capable
    # column (#427), keyed by col_name like the visibility map. Edited
    # in the pane's Column Ack Wait Times grid; 0 = don't wait. Seeded
    # with the tree's builtin Routes column for now — plugin-provided
    # defaults register in a later increment.
    protocol_tree_ack_times = Dict(Str, Float)

    def _protocol_tree_ack_times_default(self):
        return {"Routes": 5.0}

    @classmethod
    def ensure(cls, preferences=None):
        """Return ``preferences`` unchanged, or a standalone helper bound
        to the global default node — the demo / headless-test fallback
        used by views that may be constructed without the dock pane."""
        return preferences if preferences is not None else cls()

    def _PROTOCOL_REPO_DIR_default(self) -> Path:
        default_dir = Path(ETSConfig.user_data) / "Protocols"

        default_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Default repo directory is: {default_dir}")

        return default_dir


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
                 low=ACK_TIMEOUT_MIN_S, high=ACK_TIMEOUT_MAX_S,
                 decimals=1, step=0.5,
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
