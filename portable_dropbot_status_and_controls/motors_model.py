from traits.api import Button, Enum, Int, Str

from portable_dropbot_controller.consts import FILTER_POSITIONS, MOTOR_IDS
from template_status_and_controls.base_model import BaseStatusModel

from .consts import PORTABLE_DROPBOT_IMAGE


class PortableDropbotMotorsModel(BaseStatusModel):
    """Qt-free state for the motor panel: mechanism buttons, the
    advanced per-motor move inputs, and the readouts the message
    handler fills from motors_updated signals. Mutated only on the
    GUI thread."""

    DEFAULT_ICON_PATH = PORTABLE_DROPBOT_IMAGE

    # ---- Mechanisms ---------------------------------------------------
    tray_in_button = Button("Tray In")
    tray_out_button = Button("Tray Out")
    magnet_engage_button = Button("Engage")
    magnet_disengage_button = Button("Disengage")
    magnet_press_button = Button("Press")
    magnet_release_button = Button("Release")
    pogo_down_button = Button("Pogo Down")
    pogo_up_button = Button("Pogo Up")
    home_all_button = Button("Home All")
    #: Fluorescence filter wheel position; publishing on change.
    filter_position = Enum(*FILTER_POSITIONS)

    # ---- Advanced per-motor moves (steps, Int) ------------------------
    selected_motor = Enum(*MOTOR_IDS)
    move_mode = Enum("absolute", "relative")
    move_steps = Int(0)
    move_button = Button("Move")
    stop_button = Button("Stop")
    home_button = Button("Home")
    #: Collapsible-state of the advanced group (display state only).
    show_advanced = Enum(False, True)

    # ---- Readouts -----------------------------------------------------
    tray_state = Str("-")
    magnet_state = Str("-")
    filter_state = Str("-")
    pogo_state = Str("-")
    positions_display = Str("-", desc="Per-motor positions (steps)")
    homed_display = Str("-", desc="Which motors report homed")
