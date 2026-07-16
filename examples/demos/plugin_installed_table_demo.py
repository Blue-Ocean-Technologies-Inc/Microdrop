"""Minimal runner for the Manage Plugins window (issue #532).

Reuses the **real** production view + controller (``manage_plugins_view`` +
``ManagePluginsController``) and only swaps in a fake model: a
``ManagePluginsModel`` subclass that supplies sample rows and stubs the
environment-mutating worker methods so nothing runs ``pixi``. Lets you eyeball
the tabbed layout, the installed-packages table, the collapsible details pane,
and the toolbar without launching the whole app.

Run:
    pixi run python examples/demos/plugin_installed_table_demo.py
"""

import sys

from PySide6.QtWidgets import QApplication

from microdrop_style.helpers import style_app
from plugin_management.manage_model import (
    ManagePluginsModel, GroupRow, InstalledPackageRow)
from plugin_management.manage_view import manage_plugins_view
from plugin_management.manage_controller import ManagePluginsController
from plugin_management.package_installer import EnvChangeResult

# Fake channel search result (feeds the version dropdowns via apply_channel_data).
_FAKE_CHANNEL = [
    {"name": n, "version": v}
    for n, versions in {
        "heater-microdrop-plugin": ["3.11.2", "3.11.1", "3.10.0", "3.9.4"],
        "magnet-microdrop-plugin": ["1.4.0", "1.3.2", "1.3.1", "1.2.0"],
        "fluorescence-microdrop-plugin": ["0.2.1", "0.2.0", "0.1.0"],
    }.items()
    for v in versions
]


class DemoManagePluginsModel(ManagePluginsModel):
    """Fake data + no-op workers so the real view/controller run without pixi."""

    def _build_rows(self):
        return [GroupRow(name="heater_ui", label="Heater controls", enabled=True),
                GroupRow(name="magnet_ui", label="Magnet controls", enabled=False)]

    def _build_installed_rows(self):
        return [
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
        ]

    # --- stub the env-mutating workers (no pixi) ---
    def apply(self):
        print("[demo] apply groups:", self.desired())

    def pre_uninstall(self, manifest_name):
        print(f"[demo] pre_uninstall {manifest_name}")

    def do_install_version(self, dist_name, version):
        print(f"[demo] would install {dist_name}=={version}")
        return EnvChangeResult(name=dist_name, diff=None, requires_relaunch=True)

    def do_upgrade(self, dist_name):
        print(f"[demo] would upgrade {dist_name}")
        return EnvChangeResult(name=dist_name, diff=None, requires_relaunch=True)

    def do_uninstall(self, dist_name):
        print(f"[demo] would uninstall {dist_name}")
        return EnvChangeResult(name=dist_name, diff=None, requires_relaunch=True)

    def do_search_channel(self):
        print("[demo] search channel")
        return _FAKE_CHANNEL


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    style_app(app)  # loads the Material Symbols font so glyph icons render

    model = DemoManagePluginsModel()
    controller = ManagePluginsController(model=model, task=None)
    model.configure_traits(view=manage_plugins_view, handler=controller)
