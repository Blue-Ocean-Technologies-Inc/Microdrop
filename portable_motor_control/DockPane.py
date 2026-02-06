import json
from traits.api import HasTraits, Enum, Str, Button, Float, Instance, observe, Dict
from traitsui.api import View, Item, VGroup, HGroup, ButtonEditor, Spring
from pyface.tasks.api import TraitsDockPane

# Import pub/sub helper
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from portable_dropbot_controller.consts import (
    SET_TOGGLE_MOTOR,
    SET_MOTOR_HOME,
    SET_MOTOR_RELATIVE_MOVE,
    SET_MOTOR_ABSOLUTE_MOVE,
)
from .consts import PKG

# --- 1. Define Motor Data Structure ---
class MotorDef:
    def __init__(self, name, btn1_label, btn2_label, mode="toggle", max_states=2):
        self.name = name
        self.labels = (btn1_label, btn2_label)
        self.mode = mode  # "toggle" or "cycle"
        self.max_states = max_states  # Used only for "cycle" mode (e.g., 5 positions)


# Define Configuration
MOTOR_CONFIG = [
    # Toggle: True=Out, False=In
    MotorDef("tray", "In (False)", "Out (True)", mode="toggle"),
    # Cycle: Moves between indices 0-4
    MotorDef("pmt", "Prev Pos", "Next Pos", mode="cycle", max_states=5),
    # Toggle: True=Up, False=Down
    MotorDef("magnet", "Up (True)", "Down (False)", mode="toggle"),
    # Cycle: Moves between indices 0-4
    MotorDef("filter", "Prev Pos", "Next Pos", mode="cycle", max_states=5),
    # Toggle: True=Up, False=Down
    MotorDef("pogo_left", "Up (True)", "Down (False)", mode="toggle"),
    MotorDef("pogo_right", "Up (True)", "Down (False)", mode="toggle"),
]

MOTOR_MAP = {m.name: m for m in MOTOR_CONFIG}
MOTOR_NAMES = [m.name for m in MOTOR_CONFIG]


# --- 2. The Logic Model ---
class MotorControlModel(HasTraits):

    # -- Selection --
    selected_motor_name = Enum(*MOTOR_NAMES)

    # -- Dynamic Button Labels --
    btn_1_label = Str("In")
    btn_2_label = Str("Out")

    # -- Controls --
    btn_1 = Button()
    btn_2 = Button()
    home_btn = Button("Home")

    # -- Manual Move Fields --
    rel_distance = Float(10.0)
    move_rel_btn = Button("Go")
    abs_position = Float(0.0)
    move_abs_btn = Button("Go")

    # -- State Tracking for Cycling Motors --
    # Stores current index for motors like PMT/Filter locally
    _cycle_indices = Dict()

    # -- Logic --

    @observe("selected_motor_name")
    def _update_ui_context(self, event):
        """Update button labels when the motor selection changes."""
        motor_def = MOTOR_MAP[self.selected_motor_name]
        self.btn_1_label, self.btn_2_label = motor_def.labels

    def _publish(self, topic, payload):
        """Helper to serialize and publish."""
        msg = json.dumps(payload)
        print(f"Publishing to {topic}: {msg}")
        publish_message(topic, msg)

    def _btn_1_fired(self):
        """
        Toggle Mode: Sends False (State 0 / In / Down)
        Cycle Mode: Decrements Index
        """
        motor = MOTOR_MAP[self.selected_motor_name]

        if motor.mode == "toggle":
            # State False (0) is In/Down/Retracted
            self._publish(SET_TOGGLE_MOTOR, {"motor_id": motor.name, "state": 0})

        elif motor.mode == "cycle":
            # Decrement Index
            current_idx = self._cycle_indices.get(motor.name, 0)
            new_idx = (current_idx - 1) % motor.max_states
            self._cycle_indices[motor.name] = new_idx

            self._publish(SET_TOGGLE_MOTOR, {"motor_id": motor.name, "state": new_idx})

    def _btn_2_fired(self):
        """
        Toggle Mode: Sends True (State 1 / Out / Up)
        Cycle Mode: Increments Index
        """
        motor = MOTOR_MAP[self.selected_motor_name]

        if motor.mode == "toggle":
            # State True (1) is Out/Up/Extended
            self._publish(SET_TOGGLE_MOTOR, {"motor_id": motor.name, "state": 1})

        elif motor.mode == "cycle":
            # Increment Index
            current_idx = self._cycle_indices.get(motor.name, 0)
            new_idx = (current_idx + 1) % motor.max_states
            self._cycle_indices[motor.name] = new_idx

            self._publish(SET_TOGGLE_MOTOR, {"motor_id": motor.name, "state": new_idx})

    def _home_btn_fired(self):
        motor = MOTOR_MAP[self.selected_motor_name]
        # Reset local cycle index on home
        if motor.mode == "cycle":
            self._cycle_indices[motor.name] = 0

        # Send simple string or JSON depending on backend expectation.
        # Based on your backend code: `_on_motor_home_request(self, motor_id)`
        # it seems to expect just the ID string directly, not JSON.
        print(f"Homing {motor.name}...")
        publish_message(SET_MOTOR_HOME, motor.name)

    def _move_rel_btn_fired(self):
        """Send Relative Move Command"""
        motor = MOTOR_MAP[self.selected_motor_name]
        self._publish(
            SET_MOTOR_RELATIVE_MOVE,
            {"motor_id": motor.name, "move_distance": self.rel_distance},
        )

    def _move_abs_btn_fired(self):
        """Send Absolute Move Command"""
        motor = MOTOR_MAP[self.selected_motor_name]
        self._publish(
            SET_MOTOR_ABSOLUTE_MOVE,
            {"motor_id": motor.name, "move_distance": self.abs_position},
        )

    # -- View Definition --
    traits_view = View(
        VGroup(
            # 1. Motor Selector
            VGroup(
                Item("selected_motor_name", label="Target Motor"),
                show_border=True,
                label="Select Motor",
            ),
            # 2. Macros (Toggle / Cycle)
            VGroup(
                HGroup(
                    Item(
                        "btn_1",
                        editor=ButtonEditor(label_value="btn_1_label"),
                        show_label=False,
                        springy=True,
                    ),
                    Item(
                        "btn_2",
                        editor=ButtonEditor(label_value="btn_2_label"),
                        show_label=False,
                        springy=True,
                    ),
                ),
                HGroup(
                    Spring(),
                    Item("home_btn", show_label=False),
                    Spring(),
                ),
                show_border=True,
                label="Macros",
            ),
            # 3. Precision Move
            VGroup(
                HGroup(
                    Item("rel_distance", label="Move By (mm)"),
                    Item("move_rel_btn", show_label=False),
                ),
                HGroup(
                    Item("abs_position", label="Move to (mm)"),
                    Item("move_abs_btn", show_label=False),
                ),
                show_border=True,
                label="Manual Move",
            ),
        )
    )


# --- 3. The Dock Pane ---
class MotorControlDockPane(TraitsDockPane):
    id = f"{PKG}.pane"
    name = "Motor Controls"
    model = Instance(MotorControlModel, ())

    def create_contents(self, parent):
        ui = self.model.edit_traits(kind="subpanel", parent=parent)
        return ui.control


if __name__ == "__main__":
    model = MotorControlModel()
    model.configure_traits()
