"""
BaseStatusModel — shared traits and observer logic for all device panels.

Every device panel has:
  - Mode flags:  realtime_mode, protocol_running, free_mode
  - Connection:  connected, chip_inserted
  - Display:     icon_path, icon_color, connection_status_text

Subclasses add their device-specific sensor traits (voltage, temperature, …)
and override the class-level color/icon constants.

Design notes:
  - Color constants (DISCONNECTED_COLOR, etc.) are plain class attributes,
    not Traits. Subclasses override them at the class level — no __init__
    gymnastics required.
  - Hook methods (_select_icon_for_chip_state, _update_chip_display) use the
    Template Method pattern so the base observer can stay generic while each
    device customises the specific step.
"""

from traits.api import HasTraits, Bool, Str, observe, provides

from microdrop_style.colors import ERROR_COLOR, SUCCESS_COLOR, WARNING_COLOR, GREY

from .interfaces import IStatusModel


@provides(IStatusModel)
class BaseStatusModel(HasTraits):
    """
    Shared traits and observer logic for all device status-and-controls models.

    Override class-level constants in the subclass to configure colors and
    the default icon. Add device-specific Traits (sensor readings, etc.) in
    the subclass body.
    """

    # ------------------------------------------------------------------ #
    # Class-level constants — override in every subclass                   #
    # ------------------------------------------------------------------ #

    #: Icon shown when the device is disconnected.
    DEFAULT_ICON_PATH: str = ""

    #: Icon shown when a chip/device is detected (if different from default).
    CHIP_INSERTED_ICON_PATH: str = ""  # leave empty to keep DEFAULT_ICON_PATH

    #: Status icon color: device disconnected.
    DISCONNECTED_COLOR: str = GREY["lighter"]

    #: Status icon color: device connected but no chip / sample detected.
    CONNECTED_NO_DEVICE_COLOR: str = WARNING_COLOR

    #: Status icon color: device connected and chip / sample detected.
    CONNECTED_COLOR: str = SUCCESS_COLOR

    #: Status icon color: device has halted (highest priority state).
    HALTED_COLOR: str = ERROR_COLOR

    # ------------------------------------------------------------------ #
    # Mode flags (user-controllable, synced with hardware)                 #
    # ------------------------------------------------------------------ #

    realtime_mode = Bool(False, desc="Send hardware updates continuously")
    protocol_running = Bool(False, desc="A protocol is currently executing")
    free_mode = Bool(True, desc="Device is in free / manual mode")

    # ------------------------------------------------------------------ #
    # Connection state (written by the message handler)                    #
    # ------------------------------------------------------------------ #

    connected = Bool(False, desc="True when the device is connected")
    chip_inserted = Bool(False, desc="True when a chip or sample is present")
    halted = Bool(False, desc="True when the device has halted due to a fault")

    # ------------------------------------------------------------------ #
    # Derived display traits (updated automatically by observers below)   #
    # ------------------------------------------------------------------ #

    connection_status_text = Str("Inactive")
    icon_path = Str()
    icon_color = Str()

    # ------------------------------------------------------------------ #
    # Trait defaults                                                        #
    # ------------------------------------------------------------------ #

    def _icon_path_default(self):
        return self.DEFAULT_ICON_PATH

    def _icon_color_default(self):
        return self.DISCONNECTED_COLOR
    # ------------------------------------------------------------------ #
    # Observers
    # ------------------------------------------------------------------ #
    @observe("halted")
    def _on_halted_changed(self, event):
        if event.new:
            self.icon_color = self.HALTED_COLOR

    @observe("connected")
    def _on_connected_changed(self, event):
        self.connection_status_text = "Active" if event.new else "Inactive"
        self.halted = False
        if self.connected:
            self.icon_color = self.CONNECTED_NO_DEVICE_COLOR
        else:
            self.icon_color = self.DISCONNECTED_COLOR

    @observe("chip_inserted")
    def _on_chip_inserted_changed(self, event):
        # Update the icon image if the subclass provides a separate one.
        self.icon_path = self._select_icon_for_chip_state(event.new)
        # Let the subclass update any device-specific chip status traits.
        self._update_chip_display(event.new)

        if not self.halted:
            self.icon_color = self.CONNECTED_COLOR if event.new else self.CONNECTED_NO_DEVICE_COLOR

    # ------------------------------------------------------------------ #
    # Template-method hooks                                                 #
    # ------------------------------------------------------------------ #

    def _select_icon_for_chip_state(self, inserted: bool) -> str:
        """
        Return the icon path appropriate for the given chip / sample state.

        Default: returns CHIP_INSERTED_ICON_PATH when inserted (if set),
        otherwise keeps DEFAULT_ICON_PATH. Override for different behaviour.
        """
        if inserted and self.CHIP_INSERTED_ICON_PATH:
            return self.CHIP_INSERTED_ICON_PATH
        return self.DEFAULT_ICON_PATH

    def _update_chip_display(self, inserted: bool) -> None:
        """
        Override to update device-specific chip-status display traits
        (e.g. chip_status_text) when chip_inserted changes.

        Default: no-op (not all devices expose a chip status label).
        """
