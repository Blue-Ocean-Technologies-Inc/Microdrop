"""Uninstall Plugin dialog model: pick one user-installed plugin to remove.

Built from the manager's installed_plugins() list. Qt-free TraitsUI; the action
owns the orchestration (confirm + installer.uninstall_plugin)."""

from traits.api import HasTraits, Str
from traitsui.api import EnumEditor, Item, View


class UninstallPluginModel(HasTraits):
    """Single-select of a user-installed plugin to uninstall. ``selected`` is
    the chosen manifest_name."""

    selected = Str()

    def __init__(self, installed, **traits):
        super().__init__(**traits)
        # installed: list of (name, label, dist_name, group_names)
        self._installed = list(installed)
        if self._installed:
            self.selected = self._installed[0][0]

    def traits_view(self):
        # EnumEditor `values` maps each stored value (manifest_name) -> label.
        values = {name: f"{label} ({name})"
                  for name, label, _dist, _groups in self._installed}
        return View(
            Item("selected", editor=EnumEditor(values=values), show_label=False),
            buttons=["OK", "Cancel"],
            kind="livemodal",
            title="Uninstall Plugin",
            resizable=True,
        )
