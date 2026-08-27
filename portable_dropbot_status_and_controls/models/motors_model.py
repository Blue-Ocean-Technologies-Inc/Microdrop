from traits.api import Button, Enum, Int, Range, Str

from portable_dropbot_controller.consts import MOTOR_IDS
from template_status_and_controls.base_model import BaseStatusModel

from ..consts import (
    MOTOR_MACRO_LABELS, MOTOR_SPEED_UM_PER_S_BOUNDS,
    MOVE_DISTANCE_MM_BOUNDS, PORTABLE_DROPBOT_IMAGE,
)


class PortableDropbotMotorsModel(BaseStatusModel):
    """Qt-free state for the motor panel, shaped like the original
    portable pane: a target-motor selector, macro buttons that
    relabel per motor (see MOTOR_MACRO_LABELS), and manual moves in
    steps. Mutated only on the GUI thread."""

    DEFAULT_ICON_PATH = PORTABLE_DROPBOT_IMAGE

    # ---- Select Motor -------------------------------------------------
    selected_motor = Enum(*MOTOR_IDS)

    # ---- Macros (labels driven by the selection; "" hides) ------------
    macro_button_1 = Button()
    macro_button_2 = Button()
    macro_button_1_label = Str(MOTOR_MACRO_LABELS["tray"][0])
    macro_button_2_label = Str(MOTOR_MACRO_LABELS["tray"][1])
    home_button = Button("Home")
    #: The coordinated resets (cabin+mag, pushpads, filter, PMT) —
    #: mechanism macros are silently rejected until these have run
    #: after a motor-board power-up; the per-motor Home above does
    #: NOT initialize that motion coordinator.
    home_all_button = Button("Home All")

    # ---- Manual Move (mm; converted to the firmware's 0.001 mm
    # units when published; spin boxes in the view for touch use) -------
    move_by_mm = Range(*MOVE_DISTANCE_MM_BOUNDS, 1.0)
    move_by_button = Button("Go")
    move_to_mm = Range(*MOVE_DISTANCE_MM_BOUNDS, 0.0)
    move_to_button = Button("Go")
    #: Runtime-only per-motor run speed; reverts to the flashed
    #: default on reboot.
    speed_um_per_s = Range(*MOTOR_SPEED_UM_PER_S_BOUNDS, 1000,
                           mode="spinner")
    set_speed_button = Button("Set Speed")

    #: Local Prev/Next cycle position for the filter wheel, exactly
    #: like the original pane; Home resets it.
    filter_cycle_index = Int(0)
