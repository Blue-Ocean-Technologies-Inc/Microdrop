import os

from device_viewer.consts import PROTOCOL_GRID_DISPLAY_STATE, PROTOCOL_RUNNING
from microdrop_application.consts import ADVANCED_MODE_CHANGE
from portable_dropbot_controller.consts import (
    CALIBRATION_UPDATED,
    MOTOR_PARAMS_UPDATED,
    PMT_UPDATED,
    PORTABLE_DROPBOT_CONNECTED,
    PORTABLE_DROPBOT_DISCONNECTED,
    STATUS_UPDATED,
    TEMP_UPDATED,
)

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

current_folder_path = os.path.dirname(os.path.abspath(__file__))
#: Placeholder device photo (a DropBot image) until the portable
#: instrument has its own.
PORTABLE_DROPBOT_IMAGE = os.path.join(current_folder_path, "images",
                                      "portable_dropbot.png")

#: Each pane gets its own listener so the panes mount and unmount
#: independently.
MOTORS_LISTENER = f"{PKG}_motors_listener"
CALIBRATION_LISTENER = f"{PKG}_calibration_listener"
MORE_CONTROLS_LISTENER = f"{PKG}_more_controls_listener"
ADVANCED_CONTROLS_LISTENER = f"{PKG}_advanced_controls_listener"

# Topics the actors declared by this plugin subscribe to.
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
        "portable_dropbot/signals/#",
        "hardware/signals/#",
        PROTOCOL_RUNNING,
        PROTOCOL_GRID_DISPLAY_STATE,
        #: The connect row shows only in Advanced Mode.
        ADVANCED_MODE_CHANGE,
    ],
    MOTORS_LISTENER: [
        PORTABLE_DROPBOT_CONNECTED,
        PORTABLE_DROPBOT_DISCONNECTED,
        #: chip_on_pad gates the magnet macros — the firmware only
        #: moves the magnet with a chip on the pad.
        STATUS_UPDATED,
    ],
    CALIBRATION_LISTENER: [
        PORTABLE_DROPBOT_CONNECTED,
        PORTABLE_DROPBOT_DISCONNECTED,
        CALIBRATION_UPDATED,
    ],
    MORE_CONTROLS_LISTENER: [
        PORTABLE_DROPBOT_CONNECTED,
        PORTABLE_DROPBOT_DISCONNECTED,
        TEMP_UPDATED,
        PMT_UPDATED,
    ],
    #: The advanced-only pane also tracks the Edit-menu Advanced Mode
    #: toggle, which is what unlocks its controls.
    ADVANCED_CONTROLS_LISTENER: [
        PORTABLE_DROPBOT_CONNECTED,
        PORTABLE_DROPBOT_DISCONNECTED,
        MOTOR_PARAMS_UPDATED,
        ADVANCED_MODE_CHANGE,
    ],
}

#: The motor firmware moves in 0.001 mm integer units; the panel's
#: Manual Move fields take mm, like the driver's own test UI.
MM_TO_FIRMWARE_UNITS = 1000

#: Manual Move bounds (mm) — the vendor test UI's distance spin-box
#: range (negative = the other direction on relative moves).
MOVE_DISTANCE_MM_BOUNDS = (-1000.0, 1000.0)

#: Runtime run-speed bounds (µm/s): the driver measured ~40 mm/s as
#: the clean ceiling (42 mm/s stalls); the vendor UI defaults to 1000.
MOTOR_SPEED_UM_PER_S_BOUNDS = (0, 40_000)

#: Macro-button labels per target motor for the motor panel, in the
#: original portable pane's dynamic-button style: the buttons relabel
#: as the selection changes, and an empty label hides its button
#: (pmt has no macros — only Home and manual moves apply).
#: The pogo pushpads move as a coordinated pair — the hardware has no
#: per-side mechanism command (a single pad moves only via the raw
#: per-motor manual moves/home), so either pogo selection offers the
#: same Press/Release pair, labeled as the vendor's own test UI does.
#: (The driver's magnet press/release are pure aliases of
#: engage/disengage, so only the latter appear here.)
MOTOR_MACRO_LABELS = {
    "tray": ("In", "Out"),
    "pmt": ("", ""),
    "magnet": ("Engage", "Disengage"),
    "filter": ("Prev Pos", "Next Pos"),
    "pogo_left": ("Press (both)", "Release (both)"),
    "pogo_right": ("Press (both)", "Release (both)"),
}
