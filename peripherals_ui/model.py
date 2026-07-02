from traits.api import HasTraits, Str, Bool, Float, observe

from .consts import disconnected_color, connected_color


class PeripheralModel(HasTraits):
    """Holds the raw state of the zstage device."""

    # Status-bar icon colors (template contract: BaseStatusDockPane reads
    # these class-level constants when building the icon).
    DISCONNECTED_COLOR = disconnected_color
    CONNECTED_COLOR = connected_color

    device_name = Str("ZStage")
    status = Bool(False)
    position = Float(0.0)  # Position in mm
    realtime_mode = Bool(False)
    # True once a connection search has been requested (by button or menu action) this session.
    search_requested = Bool(False)
    # True while the backend's monitor thread is actively scanning for the board
    # (driven by the ZStage/signals/searching signal). Gates the status-icon click.
    searching = Bool(False)

    # Derived icon color; the base pane's _sync_model_icon_color observer
    # recolors the status-bar icon from this (template contract).
    icon_color = Str(disconnected_color)

    @observe("status")
    def _update_icon_color(self, event):
        self.icon_color = connected_color if event.new else disconnected_color
