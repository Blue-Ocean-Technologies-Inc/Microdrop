# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The device chip on the status bar's left, after the protocol chip: the
loaded device's name, washed green saved or amber while it has unsaved
edits (muted with no device loaded), opening a menu of the device file
actions.

Unsaved means what tags the pane's title " (modified)": connection,
channel and area-scale edits. Zone edits are not tracked yet."""

# Standard library imports.
from pathlib import Path

# Enthought library imports.
from traits.api import Any, HasTraits, Instance, observe

# Microdrop package imports.
from microdrop_status_bar.consts import (
    LEFT_PRIORITY_SECONDARY_FILE,
    STATUS_BAR_GROUP_FILE_CHIPS,
    STATUS_BAR_SIDE_LEFT,
)

# Microdrop style imports.
from microdrop_style.icons.icons import ICON_DEVELOPER_BOARD

# Microdrop utils imports.
from microdrop_utils.status_chip import FileChip, chip_menu, open_menu_above

# Local imports.
from ..services.svg_persistence_service import SvgPersistenceService

#: The chip's name and tooltip with no device loaded.
NO_DEVICE = "No device"
NO_DEVICE_NOTE = "No device loaded"


class DeviceChipController(HasTraits):
    """Builds the device chip and keeps it in step with the loaded device."""

    #: The device viewer dock pane: its load and save actions, and whether
    #: a protocol runs.
    dock_pane = Any()

    #: The loaded device file and whether it has unsaved edits.
    persistence = Instance(SvgPersistenceService)

    #: The chip in the status bar; None once withdrawn.
    chip = Instance(FileChip)

    def traits_init(self):
        chip = FileChip(ICON_DEVELOPER_BOARD, "deviceChip")
        chip.status_bar_side = STATUS_BAR_SIDE_LEFT
        chip.status_bar_left_priority = LEFT_PRIORITY_SECONDARY_FILE
        chip.status_bar_group = STATUS_BAR_GROUP_FILE_CHIPS
        chip.clicked.connect(self._open_menu)

        self.chip = chip

    def withdraw(self, status_bar_icons):
        """Stop following the device and take the chip out of the bar
        (``status_bar_icons``: the status-bar plugin's extension point),
        which deletes it."""
        chip = self.chip

        self.trait_set(dock_pane=None, persistence=None, chip=None)

        if chip in status_bar_icons:
            status_bar_icons.remove(chip)

        else:
            # Never placed on a bar, so nothing else deletes it.
            chip.deleteLater()

    @observe("persistence:[loaded_path, modified], chip", dispatch="ui")
    def _show_device(self, event):
        if None in (self.chip, self.persistence):
            return

        path = self.persistence.loaded_path

        if not path:
            self.chip.show_neutral(NO_DEVICE, NO_DEVICE_NOTE)

            return

        self.chip.show_file(Path(path).stem, path, self.persistence.modified)

    def _open_menu(self):
        pane = self.dock_pane
        menu = chip_menu(self.chip)

        change = menu.addAction("Change device…", pane.load_svg_dialog)
        change.setEnabled(not pane.model.protocol_running)
        menu.addAction("Save device", pane.save_svg)
        menu.addAction("Save device as…", pane.save_as_svg_dialog)

        open_menu_above(menu, self.chip)
