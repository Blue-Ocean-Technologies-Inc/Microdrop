from pyface.action.api import Action
from pyface.tasks.action.api import SGroup
from pyface.action.api import ActionItem
from traits.api import Bool, Instance, Property, observe

from microdrop_utils._logger import get_logger

logger = get_logger(__name__)

class AdvancedModeToggleAction(Action):
    """Toggle action for Advanced User Mode in main menu bar's Edit menu."""
    
    # action interface
    name = "Advanced User Mode"
    tooltip = "Enable navigation buttons during protocol execution for advanced users"
    style = "toggle"  # checkable

    # using a regular Bool trait rather than a Property to allow pyface to set it
    checked = Bool(False)
    
    # plugin reference
    plugin = Instance("protocol_grid.plugin.ProtocolGridControllerUIPlugin")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # initialize checked state from plugin if available
        if self.plugin:
            self.checked = self.plugin.get_advanced_mode_state()
            # observe for plugin state changes
            self.plugin.observe(self._on_plugin_state_changed, 'advanced_mode_changed')
    
    def perform(self, event=None):
        """Toggle advanced mode when clicked."""
        if self.plugin:
            # current_state = self.plugin.get_advanced_mode_state()
            self.plugin.set_advanced_mode_state(self.checked)
            logger.info(f"Advanced mode toggled via menu to: {self.checked}")
    
    def _on_plugin_state_changed(self, event):
        """update checked state when plugin state changes."""
        if self.plugin:
            new_state = self.plugin.get_advanced_mode_state()
            if self.checked != new_state:
                self.checked = new_state
                logger.debug(f"Menu checkmark updated to: {new_state}")

def advanced_mode_menu_factory(plugin):
    """create menu item."""
    return SGroup(
        ActionItem(action=AdvancedModeToggleAction(plugin=plugin)),
        id="advanced_mode_group"
    )