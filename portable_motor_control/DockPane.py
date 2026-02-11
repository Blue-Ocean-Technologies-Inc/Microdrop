import json
import dramatiq
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QPushButton
from traits.api import HasTraits, Enum, Str, Button, Instance, observe, Dict, Int, Bool
from traitsui.api import View, Item, VGroup, HGroup, ButtonEditor, EnumEditor
from pyface.tasks.api import TraitsDockPane

from logger.logger_service import get_logger, init_logger
from microdrop_style.helpers import get_complete_stylesheet, is_dark_mode
from microdrop_utils.dramatiq_controller_base import (
    basic_listener_actor_routine,
    generate_class_method_dramatiq_listener_actor,
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from portable_dropbot_controller.consts import (
    SET_TOGGLE_MOTOR,
    SET_MOTOR_HOME,
    SET_MOTOR_RELATIVE_MOVE,
    SET_MOTOR_ABSOLUTE_MOVE,
)
from .consts import listener_name

logger = get_logger(__name__)


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
    MotorDef("tray", "In", "Out", mode="toggle"),
    # Cycle: Moves between indices 0-4
    MotorDef("pmt", "Prev Pos", "Next Pos", mode="cycle", max_states=5),
    # Toggle: True=Up, False=Down
    MotorDef("magnet", "Up", "Down", mode="toggle"),
    # Cycle: Moves between indices 0-4
    MotorDef("filter", "Prev Pos", "Next Pos", mode="cycle", max_states=5),
    # Toggle: True=Up, False=Down
    MotorDef("pogo_left", "Up", "Down", mode="toggle"),
    MotorDef("pogo_right", "Up", "Down", mode="toggle"),
]

MOTOR_MAP = {m.name: m for m in MOTOR_CONFIG}
MOTOR_NAMES = [m.name for m in MOTOR_CONFIG]
MOTOR_COOLDOWN_SEC = 5


# --- 2. The Logic Model ---
class MotorControlModel(HasTraits):

    # -- Connection state (from server: dropbot/signals/connected, disconnected) --
    connected = Bool(False, desc="True when DropBot is connected")

    # -- Cooldown after motor action to prevent double-clicks --
    motor_busy = Bool(False, desc="True during motor move cooldown")

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
    rel_distance = Int(10)
    move_rel_btn = Button("Go")
    abs_position = Int(0)
    move_abs_btn = Button("Go")

    # -- State Tracking for Cycling Motors --
    # Stores current index for motors like PMT/Filter locally
    _cycle_indices = Dict()


# -- View Definition --
motors_view = View(
    VGroup(
        # 1. Motor Selector
        VGroup(
            Item(
                "selected_motor_name",
                label="Target Motor",
                editor=EnumEditor(values={m: m for m in MOTOR_NAMES}),
            ),
            show_border=True,
            label="Select Motor",
            enabled_when="connected and not motor_busy",
        ),
        # 2. Macros (Toggle / Cycle)
        VGroup(
            HGroup(
                Item(
                    "btn_1",
                    editor=ButtonEditor(label_value="btn_1_label"),
                    show_label=False,
                    springy=False,
                ),
                Item(
                    "btn_2",
                    editor=ButtonEditor(label_value="btn_2_label"),
                    show_label=False,
                    springy=False,
                ),
                Item("home_btn", show_label=False, springy=False),
            ),
            show_border=True,
            label="Macros",
            enabled_when="connected and not motor_busy",
        ),
        # 3. Precision Move
        VGroup(
            HGroup(
                Item("rel_distance", label="Move By (\u03bcm)"),
                Item("move_rel_btn", show_label=False, springy=False),
            ),
            HGroup(
                Item("abs_position", label="Move To (\u03bcm)"),
                Item("move_abs_btn", show_label=False, springy=False),
            ),
            padding=0,
            show_border=True,
            label="Manual Move",
            enabled_when="connected and not motor_busy",
        ),
    ),
    resizable=True,
)


# --- 3. Connection Listener (server messages -> model.connected) ---
class MotorControlConnectionListener(HasTraits):
    """Listens to dropbot/signals/connected and disconnected, updates model.connected."""

    model = Instance(MotorControlModel)
    dramatiq_listener_actor = Instance(dramatiq.Actor)

    def traits_init(self):
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=listener_name,
            class_method=self.listener_actor_routine,
        )

    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(
            self, message, topic,
            handler_name_pattern="_on_{topic}_triggered",
        )

    def _on_connected_triggered(self, body):
        if self.model:
            self.model.connected = True

    def _on_disconnected_triggered(self, body):
        if self.model:
            self.model.connected = False


# --- 4. The Dock Pane (Controller)---
class MotorControlDockPane(TraitsDockPane):
    id = "motor_controls.pane"
    name = "Motor Controls"
    model = Instance(MotorControlModel, ())

    traits_view = motors_view

    def __init__(self, **traits):
        super().__init__(**traits)
        self._connection_listener = MotorControlConnectionListener(model=self.model)
        self._motor_cooldown_timer = None

    def _apply_motor_pane_theme(self):
        """Apply compact stylesheet. Macro buttons: short bar."""
        if not hasattr(self, "control") or self.control is None:
            return
        theme = "dark" if is_dark_mode() else "light"
        try:
            # TraitsDockPane may wrap control; get the actual widget
            widget = self.control.widget() if hasattr(self.control, "widget") else self.control
            if widget is None:
                return
            widget.setObjectName("motor_control_pane")
            for btn in widget.findChildren(QPushButton):
                if btn.text() == "Home":
                    btn.setToolTip("Home")
                    break
            # Use small button base for compact look; override for macro buttons
            base = get_complete_stylesheet(theme, button_type="small")
            override = """
            #motor_control_pane QPushButton {
                font-family: "Inter", sans-serif;
                font-size: 10pt;
                min-height: 22px;
                max-height: 26px;
                min-width: 72px;
                max-width: 100px;
                padding: 2px 8px;
            }
            """
            widget.setStyleSheet(base + override)
        except Exception:
            pass

    @observe("control")
    def _apply_motor_pane_stylesheet(self, event):
        """Apply same stylesheet as device viewer for consistency."""
        if event.new is not None:
            self._apply_motor_pane_theme()
            QApplication.styleHints().colorSchemeChanged.connect(self._apply_motor_pane_theme)

    def _start_motor_cooldown(self):
        """Disable motor controls briefly after any motor action."""
        self.model.motor_busy = True
        if self._motor_cooldown_timer:
            self._motor_cooldown_timer.stop()
        self._motor_cooldown_timer = QTimer()
        self._motor_cooldown_timer.setSingleShot(True)
        self._motor_cooldown_timer.timeout.connect(self._clear_motor_cooldown)
        self._motor_cooldown_timer.start(MOTOR_COOLDOWN_SEC * 1000)

    def _clear_motor_cooldown(self):
        if hasattr(self, "model") and self.model is not None:
            self.model.motor_busy = False
        self._motor_cooldown_timer = None

    ##################################################################
    ### Controller Interface
    ##################################################################

    # ----- Helpers method ----------------------------
    @staticmethod
    def _publish(topic, payload):
        """Helper to serialize and publish."""
        msg = json.dumps(payload)
        logger.info(f"Publishing to {topic}: {msg}")
        publish_message(message=msg, topic=topic)

    ## ----- Trait Observers -------------- ######

    @observe("model:selected_motor_name")
    def _update_ui_context(self, event):
        """Update button labels when the motor selection changes."""
        motor_def = MOTOR_MAP[self.model.selected_motor_name]
        self.model.btn_1_label, self.model.btn_2_label = motor_def.labels

    @observe("model:btn_1")
    def _btn_1_fired(self, event):
        """
        Toggle Mode: Sends False
        Cycle Mode: Decrements Index
        """
        self._start_motor_cooldown()
        motor = MOTOR_MAP[self.model.selected_motor_name]

        if motor.mode == "toggle":
            # State False (0) is In/Down/Retracted
            self._publish(SET_TOGGLE_MOTOR, {"motor_id": motor.name, "state": 0})

        elif motor.mode == "cycle":
            # Decrement Index
            current_idx = self.model._cycle_indices.get(motor.name, 0)
            new_idx = (current_idx - 1) % motor.max_states
            self.model._cycle_indices[motor.name] = new_idx

            self._publish(SET_TOGGLE_MOTOR, {"motor_id": motor.name, "state": new_idx})

    @observe("model:btn_2")
    def _btn_2_fired(self, event):
        """
        Toggle Mode: Sends True
        Cycle Mode: Increments Index
        """
        self._start_motor_cooldown()
        motor = MOTOR_MAP[self.model.selected_motor_name]

        if motor.mode == "toggle":
            # State True (1) is Out/Up/Extended
            self._publish(SET_TOGGLE_MOTOR, {"motor_id": motor.name, "state": 1})

        elif motor.mode == "cycle":
            # Increment Index
            current_idx = self.model._cycle_indices.get(motor.name, 0)
            new_idx = (current_idx + 1) % motor.max_states
            self.model._cycle_indices[motor.name] = new_idx

            self._publish(SET_TOGGLE_MOTOR, {"motor_id": motor.name, "state": new_idx})

    @observe("model:home_btn")
    def _home_btn_fired(self, event):
        self._start_motor_cooldown()
        motor = MOTOR_MAP[self.model.selected_motor_name]
        # Reset local cycle index on home
        if motor.mode == "cycle":
            self.model._cycle_indices[motor.name] = 0

        logger.info(f"Homing {motor.name}...")
        publish_message(topic=SET_MOTOR_HOME, message=motor.name)

    @observe("model:move_rel_btn")
    def _move_rel_btn_fired(self, event):
        """Send Relative Move Command"""
        self._start_motor_cooldown()
        motor = MOTOR_MAP[self.model.selected_motor_name]
        self._publish(
            SET_MOTOR_RELATIVE_MOVE,
            {"motor_id": motor.name, "move_distance": self.model.rel_distance},
        )

    @observe("model:move_abs_btn")
    def _move_abs_btn_fired(self, event):
        """Send Absolute Move Command"""
        self._start_motor_cooldown()
        motor = MOTOR_MAP[self.model.selected_motor_name]
        self._publish(
            SET_MOTOR_ABSOLUTE_MOVE,
            {"motor_id": motor.name, "move_distance": self.model.abs_position},
        )


if __name__ == "__main__":
    init_logger()
    MotorControlDockPane().configure_traits()
