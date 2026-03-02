from template_status_and_controls.base_controller import BaseStatusController


class ControlsController(BaseStatusController):
    """OpenDrop controls controller.

    All logic (realtime-mode toggle, message queueing, debounced setattr)
    is inherited from BaseStatusController. OpenDrop has no additional
    hardware parameters to control from the UI.
    """
