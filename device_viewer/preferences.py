import filecmp
from pathlib import Path

# Enthought library imports.
from apptools.preferences.api import PreferencesHelper
from envisage.ui.tasks.api import PreferencesCategory, PreferencesPane
from microdrop_application.preferences_dialog import advanced_mode_tab
from traits.api import Button, Dict, Directory, File, Float, Instance, Property, Range, Bool, Str, observe
from traits.etsconfig.api import ETSConfig
from traitsui.api import FileEditor, Group, HGroup, Item, View
from pyface.qt.QtCore import QTimer

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from logger.logger_service import get_logger
from microdrop_utils.file_handler import safe_copy_file
from microdrop_utils.preferences_UI_helpers import (
    create_grid_group,
    create_item_label_group,
    create_item_label_pair,
)

logger = get_logger(__name__)

from microdrop_style.text_styles import preferences_group_style_sheet

from .consts import (
    ALPHA_VIEW_MIN_HEIGHT,
    AUTO_FIT_MARGIN_SCALE,
    DEVICE_VIEWER_SIDEBAR_WIDTH,
    LAYERS_VIEW_MIN_HEIGHT,
    MASTER_SVG_FILE,
    PIN_MAP_SVG_FILE,
    NUMBER_OF_CHANNELS,
    ZOOM_SENSITIVITY,
    GAMEPAD_CAPTURE_REQUEST,
    GAMEPAD_BTN_CLEAR,
    GAMEPAD_BTN_FIND,
    GAMEPAD_BTN_SPLIT,
    GAMEPAD_BTN_ADD,
    GAMEPAD_BTN_REMOVE,
    GAMEPAD_BTN_REALTIME,
    GAMEPAD_DEBOUNCE_MOVE_SPLIT_S,
    GAMEPAD_DEBOUNCE_ADD_REMOVE_S,
    GAMEPAD_DEBOUNCE_FIND_S,
    GAMEPAD_DEBOUNCE_REALTIME_S,
    GAMEPAD_AXIS_THRESHOLD,
    GAMEPAD_RECONNECT_REQUEST,
)
from .default_settings import default_alphas, default_visibility


class DeviceViewerPreferences(PreferencesHelper):
    """The preferences helper, inspired by envisage one for the Attractors application.
    The underlying preference object is the global default since we do not pass a
    Preference object. See source code for PreferencesHelper for more details."""

    #### 'PreferencesHelper' interface ########################################

    # The path to the preference node that contains the preferences.
    preferences_path = "microdrop.device_viewer"

    #### Preferences ##########################################################
    ### Side bar prefs ###
    DEVICE_VIEWER_SIDEBAR_WIDTH = Range(
        value=DEVICE_VIEWER_SIDEBAR_WIDTH, low=0, high=10000
    )
    ALPHA_VIEW_MIN_HEIGHT = Range(value=ALPHA_VIEW_MIN_HEIGHT, low=0, high=10000)
    LAYERS_VIEW_MIN_HEIGHT = Range(value=LAYERS_VIEW_MIN_HEIGHT, low=0, high=10000)

    default_visibility = Dict(default_visibility)
    default_alphas = Dict(default_alphas)

    ### Recording viewer (video_viewer pane) prefs ###
    # Persisted zoom/pan of the playback canvas — the alignment transform
    # can push the frame outside the pane's bounds, so the user's chosen
    # framing must survive reloads. zoom 0.0 = unset (fit to view).
    video_viewer_zoom = Float(0.0)
    video_viewer_center_x = Float(0.0)
    video_viewer_center_y = Float(0.0)

    ### main view prefs ###
    AUTO_FIT_MARGIN_SCALE = Range(
        value=AUTO_FIT_MARGIN_SCALE, low=1, high=100, mode="spinner"
    )
    ZOOM_SENSITIVITY = Range(value=ZOOM_SENSITIVITY, low=1, high=100, mode="spinner")

    # Number of electrode channels (valid channel indices 0 to NUMBER_OF_CHANNELS - 1)
    NUMBER_OF_CHANNELS = Range(
        value=NUMBER_OF_CHANNELS, low=1, high=1024, mode="spinner"
    )

    # getters for processed values from int set in spinner
    _auto_fit_margin_scale = Property(observe="AUTO_FIT_MARGIN_SCALE")
    _zoom_scale = Property(observe="ZOOM_SENSITIVITY")

    ### Gamepad prefs ###
    # Persisted button indices. The interaction service reads these (with
    # MICRODROP_GAMEPAD_* env vars taking precedence) and reloads live when they
    # change. SDL exposes up to 32 buttons; 0-31 is a safe range.
    gamepad_btn_clear = Range(value=GAMEPAD_BTN_CLEAR, low=0, high=31, mode="spinner")
    gamepad_btn_find = Range(value=GAMEPAD_BTN_FIND, low=0, high=31, mode="spinner")
    gamepad_btn_split = Range(value=GAMEPAD_BTN_SPLIT, low=0, high=31, mode="spinner")
    gamepad_btn_add = Range(value=GAMEPAD_BTN_ADD, low=0, high=31, mode="spinner")
    gamepad_btn_remove = Range(value=GAMEPAD_BTN_REMOVE, low=0, high=31, mode="spinner")
    gamepad_btn_realtime = Range(value=GAMEPAD_BTN_REALTIME, low=0, high=31, mode="spinner")

    # Persisted debounce timings (seconds) and analog-stick threshold.
    gamepad_debounce_move_split = Range(value=GAMEPAD_DEBOUNCE_MOVE_SPLIT_S, low=0.0, high=3.0)
    gamepad_debounce_add_remove = Range(value=GAMEPAD_DEBOUNCE_ADD_REMOVE_S, low=0.0, high=3.0)
    gamepad_debounce_find = Range(value=GAMEPAD_DEBOUNCE_FIND_S, low=0.0, high=5.0)
    gamepad_debounce_realtime = Range(value=GAMEPAD_DEBOUNCE_REALTIME_S, low=0.0, high=5.0)
    gamepad_axis_threshold = Range(value=GAMEPAD_AXIS_THRESHOLD, low=0.1, high=1.0)

    # Transient capture-mode UI state. Trailing underscore keeps these OUT of the
    # preferences node (see PreferencesHelper._is_preference_trait), so the Button
    # clicks and the prompt label are never persisted.
    capture_prompt_ = Str()
    # Single-shot timer that auto-clears the prompt. Not every capture outcome
    # writes a binding (timeout, cancel, reconnect), so the prompt can't rely on
    # _gamepad_binding_changed alone to clear. Trailing underscore => not persisted.
    _capture_prompt_timer_ = Instance(QTimer)
    rebind_clear_ = Button("Rebind")
    rebind_find_ = Button("Rebind")
    rebind_split_ = Button("Rebind")
    rebind_add_ = Button("Rebind")
    rebind_remove_ = Button("Rebind")
    rebind_realtime_ = Button("Rebind")
    reconnect_gamepad_ = Button("Reconnect controller")

    DEFAULT_SVG_FILE = File

    DEVICE_REPO_DIR = Directory()

    def _DEVICE_REPO_DIR_default(self) -> Path:
        default_dir = Path(ETSConfig.user_data) / "Devices"

        default_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Default repo directory is: {default_dir}")

        # Seed the repo with the bundled device files on first run. Only copy a
        # file that is missing so user-modified copies are never clobbered.
        for source_file in (MASTER_SVG_FILE, PIN_MAP_SVG_FILE):
            destination = default_dir / source_file.name
            if not destination.exists():
                if source_file.exists():
                    logger.info(f"Missing {source_file.name} in device repo.\nCopying {source_file} to {destination}")
                    safe_copy_file(str(source_file), str(destination))
                else:
                    logger.error(f"Bundled device file not found: {source_file}")

        return default_dir

    def _DEFAULT_SVG_FILE_default(self):
        # --- Define Master File Path (local to the script) ---
        logger.debug(f"Master svg file is located at: {MASTER_SVG_FILE}")

        if not MASTER_SVG_FILE.exists():
            logger.error("Master file not found!.")
            raise FileNotFoundError("Master file not found!.")

        # --- Ensure User's File is a Copy of Master on First Run ---
        default_user_file = Path(self.DEVICE_REPO_DIR) / MASTER_SVG_FILE.name
        logger.debug(f"Checking for user's default file: {default_user_file}")

        should_overwrite = True

        if default_user_file.exists():
            # If the user's file exists, check if it's different from master

            if filecmp.cmp(MASTER_SVG_FILE, default_user_file, shallow=False):
                logger.info("User's file already exists and matches master.")
                should_overwrite = False

            else:
                logger.info(
                    "User's default svg file exists but is different from master. Overwriting..."
                )

        else:
            logger.info("User's default svg file not found, creating it from master...")

        if should_overwrite:
            default_user_file = safe_copy_file(
                str(MASTER_SVG_FILE), str(default_user_file)
            )

        return str(default_user_file)

    def _get__auto_fit_margin_scale(self) -> float:
        return self.AUTO_FIT_MARGIN_SCALE / 100

    def _get__zoom_scale(self) -> float:
        return 1 + (self.ZOOM_SENSITIVITY / 100)

    # ---- Gamepad live button-capture (remap) ----
    def _set_capture_prompt(self, text: str, timeout_ms: int = 11000) -> None:
        """Set the prompt label and auto-clear it after ``timeout_ms``.

        A non-binding outcome (capture timeout/cancel, reconnect) never writes a
        preference, so the timer is what clears those prompts; a successful
        capture clears it earlier via _gamepad_binding_changed.
        """
        self.capture_prompt_ = text
        timer = self._capture_prompt_timer_
        if timer is None:
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self.trait_set(capture_prompt_=""))
            self._capture_prompt_timer_ = timer
        if text:
            timer.start(timeout_ms)
        else:
            timer.stop()

    def _request_gamepad_capture(self, action: str) -> None:
        """Ask the live interaction service to capture the next button press.

        The service writes the captured index back into the matching
        gamepad_btn_* preference, which syncs to this instance via the
        preferences node and clears the prompt (see _gamepad_binding_changed).
        """
        self._set_capture_prompt(
            f"Press a gamepad button to assign to '{action}'… "
            f"(no press within ~10s cancels)"
        )
        publish_message(topic=GAMEPAD_CAPTURE_REQUEST, message=action)

    def _rebind_clear__fired(self):
        self._request_gamepad_capture("clear")

    def _rebind_find__fired(self):
        self._request_gamepad_capture("find")

    def _rebind_split__fired(self):
        self._request_gamepad_capture("split")

    def _rebind_add__fired(self):
        self._request_gamepad_capture("add")

    def _rebind_remove__fired(self):
        self._request_gamepad_capture("remove")

    def _rebind_realtime__fired(self):
        self._request_gamepad_capture("realtime")

    def _reconnect_gamepad__fired(self):
        """Ask the live service to re-attempt controller acquisition.

        Result is reflected by the status-bar joystick icon; the prompt is just
        transient feedback and auto-clears.
        """
        self._set_capture_prompt("Attempting to reconnect controller…", timeout_ms=2500)
        publish_message(topic=GAMEPAD_RECONNECT_REQUEST, message="")

    @observe(
        "gamepad_btn_clear, gamepad_btn_find, gamepad_btn_split, "
        "gamepad_btn_add, gamepad_btn_remove, gamepad_btn_realtime"
    )
    def _gamepad_binding_changed(self, event):
        """Clear the capture prompt once a binding actually changes.

        Fires both for manual spinner edits and when the service writes a
        freshly captured button into the preference node.
        """
        self._set_capture_prompt("")


device_viewer_tab = PreferencesCategory(
    id="microdrop.device_viewer.preferences",
    name="Device Viewer",
)

# Define device viewer preferences pane view contents

# This is the list of trait names for the grid layout
sidebar_setting_items = [
    "DEVICE_VIEWER_SIDEBAR_WIDTH",
    "ALPHA_VIEW_MIN_HEIGHT",
    "LAYERS_VIEW_MIN_HEIGHT",
]

# Create the grid group for the sidebar items.
sidebar_settings_grid = create_grid_group(
    sidebar_setting_items,
    group_label="Sidebar View",
    group_show_border=True,  # Example of passing a group kwarg
    group_style_sheet=preferences_group_style_sheet,
)

########## Main view grid ###########################
# Create items for the default svg for the main view group.
default_svg_setting_item = create_item_label_pair(
    "DEFAULT_SVG_FILE",
    label_text="Default Device Layout",
    item_editor=FileEditor(
        filter=["SVG Files (*.svg)|*.svg|All Files (*.*)|*.*"], dialog_style="open"
    ),
)

default_auto_fit_margin_scale_item = create_item_label_group(
    "AUTO_FIT_MARGIN_SCALE",
)

default_zoom_sensitivity = create_item_label_group(
    "ZOOM_SENSITIVITY",
)

default_number_of_channels = create_item_label_group(
    "NUMBER_OF_CHANNELS",
    label_text="Number of channels",
)

main_view_settings = (
    Group(
        [
            default_svg_setting_item,
            default_auto_fit_margin_scale_item,
            default_zoom_sensitivity,
            default_number_of_channels,
        ],
        label="Main View",
        show_labels=False,
        show_border=True,
        style_sheet=preferences_group_style_sheet,
    ),
)

########## Gamepad settings ###########################
def _gamepad_button_row(trait_name: str, rebind_trait: str, label: str) -> HGroup:
    """A button-index spinner paired with a live 'Rebind' capture button."""
    return HGroup(
        Item(trait_name, label=label),
        Item(rebind_trait, show_label=False, tooltip="Press, then press a button on the gamepad"),
    )


gamepad_settings = Group(
    Group(
        HGroup(
            Item("capture_prompt_", style="readonly", show_label=False, springy=True),
            Item("reconnect_gamepad_", show_label=False,
                 tooltip="Re-attempt connection after unplugging/replugging the controller"),
        ),
        _gamepad_button_row("gamepad_btn_clear", "rebind_clear_", "Clear all (A)"),
        _gamepad_button_row("gamepad_btn_find", "rebind_find_", "Find liquid (Select)"),
        _gamepad_button_row("gamepad_btn_split", "rebind_split_", "Split — hold (B)"),
        _gamepad_button_row("gamepad_btn_add", "rebind_add_", "Add — hold (Y)"),
        _gamepad_button_row("gamepad_btn_remove", "rebind_remove_", "Remove — hold (X)"),
        _gamepad_button_row("gamepad_btn_realtime", "rebind_realtime_", "Realtime toggle (Start)"),
        label="Button mapping",
        show_border=True,
    ),
    Group(
        Item("gamepad_debounce_move_split", label="Move / split (s)"),
        Item("gamepad_debounce_add_remove", label="Add / remove (s)"),
        Item("gamepad_debounce_find", label="Find liquid (s)"),
        Item("gamepad_debounce_realtime", label="Realtime toggle (s)"),
        Item("gamepad_axis_threshold", label="Analog-stick threshold"),
        label="Timing & sensitivity",
        show_border=True,
    ),
    label="Gamepad",
    show_border=True,
    style_sheet=preferences_group_style_sheet,
)

class DeviceViewerPreferencesPane(PreferencesPane):
    """Device Viewer preferences pane based on enthought envisage's The preferences pane for the Attractors application."""

    #### 'PreferencesPane' interface ##########################################

    # The factory to use for creating the preferences model object.
    model_factory = DeviceViewerPreferences

    category = device_viewer_tab.id

    ########################################################################################

    view = View(
        Item("_"),  # Separator
        main_view_settings,
        Item("_"),  # Separator
        sidebar_settings_grid,
        Item("_"),  # Separator
        gamepad_settings,
        Item("_"),
        resizable=True,
    )

#### Advanced Mode preferences (shown only when Advanced Mode is enabled)

class DeviceViewerAdvancedPreferences(PreferencesHelper):
    """The preferences helper, inspired by envisage one for the Attractors application.
    The underlying preference object is the global default since we do not pass a
    Preference object. See source code for PreferencesHelper for more details."""

    #### 'PreferencesHelper' interface ########################################

    # The path to the preference node that contains the preferences.
    preferences_path = "microdrop.device_viewer.advanced"

    #### Preferences ##########################################################
    allow_hardware_disables = Bool(True)


class DeviceViewerAdvancedPreferencesPane(PreferencesPane):
    """Advanced mode preferences pane. Only visible when Advanced Mode is toggled on."""

    model_factory = DeviceViewerAdvancedPreferences

    category = advanced_mode_tab.id

    view = View(
        Item("_"),  # Separator
            Group(
                Item(
                    "allow_hardware_disables",
                    tooltip=(
                        "When enabled, the device viewer will visually reflect channels that the hardware "
                        "has reported as disabled (e.g., due to detected shorts or actuation faults). "
                        "Disabled channels will appear greyed out and non-interactive in the device view.\n\n"
                        "When disabled, hardware-reported channel disables are ignored by the device viewer "
                        "and all channels remain visually active regardless of hardware state.\n\n"
                        "WARNING: Disabling this setting means you will NOT see visual feedback when the "
                        "hardware disables channels for safety reasons. Only change this if you understand "
                        "the implications for your experiment."
                    ),
                ),
                label="Device Viewer",
                show_border=True,
                style_sheet=preferences_group_style_sheet,
            ),
        Item("_"),
        resizable=True,
    )