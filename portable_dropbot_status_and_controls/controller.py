from template_status_and_controls.base_controller import BaseStatusController


class ControlsController(BaseStatusController):
    """Portable DropBot controls controller.

    All logic (realtime-mode toggle, message queueing, debounced setattr)
    is inherited from BaseStatusController. The portable dropbot has no
    additional hardware parameters to control from the UI (voltage and
    frequency are on-board).
    """
