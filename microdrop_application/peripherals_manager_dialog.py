"""Tools-menu dialog model for hot loading/unloading the magnet-peripheral
plugin groups.

Two independent checkboxes — Magnet UI and Magnet Backend — applied on OK by
the caller (ManagePeripheralsAction) via PluginGroupManager.apply(). The model
is intentionally Qt-free TraitsUI; the action owns the orchestration.
"""

from traits.api import Bool, HasTraits
from traitsui.api import Item, View


class PeripheralsManagerModel(HasTraits):
    """Checkbox state for the Manage Peripherals dialog."""

    magnet_ui_enabled = Bool()
    magnet_backend_enabled = Bool()

    traits_view = View(
        Item(
            "magnet_ui_enabled",
            label="Magnet UI (dock pane, status icon, protocol column)",
        ),
        Item(
            "magnet_backend_enabled",
            label="Magnet Backend (controller + connection search)",
        ),
        buttons=["OK", "Cancel"],
        kind="livemodal",
        title="Manage Peripherals",
        resizable=True,
    )
