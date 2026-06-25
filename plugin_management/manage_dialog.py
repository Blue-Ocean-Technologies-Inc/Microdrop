"""Manage Plugins dialog model: one checkbox per registered plugin group.

Built dynamically from the live group list (name, label, loaded) — adds a Bool
trait per group and a programmatic TraitsUI view. Qt-free; the action owns the
orchestration (apply on OK)."""

from traits.api import Bool, HasTraits
from traitsui.api import Item, Label, VGroup, View


def _trait_name(group_name):
    return "grp__" + group_name


class PluginsManagerModel(HasTraits):
    """Checkbox state for the Manage Plugins dialog. ``groups`` is a list of
    (group_name, label, loaded) tuples."""

    def __init__(self, groups, **traits):
        super().__init__(**traits)
        self._group_names = [name for name, _label, _loaded in groups]
        self._group_labels = {name: label for name, label, _loaded in groups}
        for name, _label, loaded in groups:
            self.add_trait(_trait_name(name), Bool(loaded))

    def desired(self):
        """{group_name: checkbox bool} for every listed group."""
        return {name: getattr(self, _trait_name(name)) for name in self._group_names}

    def traits_view(self):
        if self._group_names:
            items = [
                Item(_trait_name(name), label=self._group_labels[name])
                for name in self._group_names
            ]
        else:
            items = [Label("No optional plugins are installed.")]
        return View(
            VGroup(*items, label="Enable plugin groups", show_border=True),
            buttons=["OK", "Cancel"],
            kind="livemodal",
            title="Manage Plugins",
            resizable=True,
        )
