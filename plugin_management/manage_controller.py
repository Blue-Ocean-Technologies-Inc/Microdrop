"""Handler for the Manage Plugins dialog: OK applies the toggled state."""
from traitsui.api import Controller

from logger.logger_service import get_logger

logger = get_logger(__name__)


class ManagePluginsController(Controller):
    """On OK, reconcile the group manager to the dialog's checkboxes. The
    dock panes / menu bar / topic routing all follow reactively."""

    def closed(self, info, is_ok):
        if not is_ok:
            return
        model = info.object
        desired = model.desired()
        logger.info(f"Manage Plugins: applying {desired}")
        model.manager.apply(model.application, desired)
