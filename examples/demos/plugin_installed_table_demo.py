"""Minimal runner for the Manage Plugins → Installed Packages tab (issue #532).

Uses the **real** production components — ``InstalledPackageRow`` +
``format_installed_details_html`` from the model, ``installed_table_editor`` /
``groups_table`` from the view — with fake data and a throwaway demo handler, so
the split table+details layout, the reload-glyph toolbar, and the columns render
exactly as in the app but no real pixi install/uninstall runs (the row Events
just print + update a status line).

Run:
    pixi run python examples/demos/plugin_installed_table_demo.py
"""

import sys

from PySide6.QtWidgets import QApplication, QToolBar
from PySide6.QtGui import QFont

from traits.api import HasTraits, List, Str, Instance, observe
from traitsui.api import (Action, HSplit, HTMLEditor, Item, Tabbed, ToolBar,
                          UItem, VGroup, View)

from microdrop_style.helpers import style_app
from microdrop_style.button_styles import ICON_FONT_FAMILY
from microdrop_style.icons.icons import ICON_REFRESH
from microdrop_utils.traitsui_qt_helpers import SafeCancelTableHandler
from plugin_management.manage_model import (
    GroupRow, InstalledPackageRow, format_installed_details_html)
from plugin_management.manage_view import groups_table
from plugin_management.installed_table import installed_table_editor


class _DemoHandler(SafeCancelTableHandler):
    def init(self, info):
        super().init(info)
        control = getattr(info.ui, "control", None)
        if control is not None:
            for tb in control.findChildren(QToolBar):
                tb.setFont(QFont(ICON_FONT_FAMILY, 16))
        return True

    def refresh_versions(self, info):
        info.object.status = "Refresh versions (demo: no-op)."
        print(info.object.status)


class InstalledTableDemo(HasTraits):
    rows = List(Instance(GroupRow))
    installed_rows = List(Instance(InstalledPackageRow))
    installed_selected = Instance(InstalledPackageRow)
    installed_details_text = Str()
    status = Str("Ready.")

    view = View(
        Tabbed(
            VGroup(
                UItem("rows", editor=groups_table),
                label="Available Groups",
            ),
            HSplit(
                Item("installed_rows", show_label=False, editor=installed_table_editor),
                Item("installed_details_text", show_label=False, style="custom",
                     editor=HTMLEditor(open_externally=True)),
                label="Installed Packages",
            ),
        ),
        UItem("status", style="readonly"),
        toolbar=ToolBar(Action(name=ICON_REFRESH, action="refresh_versions",
                               tooltip="Refresh available versions")),
        title="Manage Plugins — Installed Packages (demo)",
        width=680, height=380, resizable=True,
        handler=_DemoHandler(),
    )

    @observe("installed_selected")
    def _details(self, event):
        self.installed_details_text = (
            format_installed_details_html(self.installed_selected)
            if self.installed_selected else "")

    @observe("installed_rows:items:open_docs")
    def _open_docs(self, event):
        row = event.object
        self.status = f"[docs] {row.name} → {row.doc_url or '(no URL — not yet published)'}"
        print(self.status)

    @observe("installed_rows:items:upgrade")
    def _upgrade(self, event):
        row = event.object
        latest = row.available_versions[0] if row.available_versions else row.version
        self.status = f"Would upgrade {row.name} → {latest}, then relaunch."
        print(self.status)

    @observe("installed_rows:items:uninstall")
    def _uninstall(self, event):
        row = event.object
        self.status = f"Would uninstall {row.name}, then relaunch."
        print(self.status)

    @observe("installed_rows:items:version")
    def _version(self, event):
        row = event.object
        self.status = f"Would install {row.name}=={event.new}, then relaunch."
        print(self.status)


def _sample():
    return InstalledTableDemo(
        rows=[
            GroupRow(name="heater_ui", label="Heater controls", enabled=True),
            GroupRow(name="magnet_ui", label="Magnet controls", enabled=False),
        ],
        installed_rows=[
            InstalledPackageRow(
                name="heater-microdrop-plugin", dist_name="heater-microdrop-plugin",
                label="Heater", manifest_name="heater", version="3.11.2",
                group_names=["heater_ui", "heater_backend"],
                available_versions=["3.11.2", "3.11.1", "3.10.0", "3.9.4"],
                doc_url="https://github.com/Blue-Ocean-Technologies-Inc/heater-microdrop-plugin"),
            InstalledPackageRow(
                name="magnet-microdrop-plugin", dist_name="magnet-microdrop-plugin",
                label="Magnet", manifest_name="magnet", version="1.4.0",
                group_names=["magnet_ui"],
                available_versions=["1.4.0", "1.3.2", "1.3.1", "1.2.0"],
                doc_url="https://github.com/Blue-Ocean-Technologies-Inc/magnet-microdrop-plugin"),
            InstalledPackageRow(
                name="fluorescence-microdrop-plugin", dist_name="fluorescence-microdrop-plugin",
                label="Fluorescence", manifest_name="fluorescence", version="0.2.1",
                group_names=["fluorescence_ui"],
                available_versions=["0.2.1", "0.2.0", "0.1.0"],
                doc_url=""),  # not yet published — greyed docs glyph + tooltip
        ],
    )


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    style_app(app)  # loads the Material Symbols font so glyph icons render
    _sample().configure_traits()
