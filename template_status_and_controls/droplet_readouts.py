# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Droplet readouts for an instrument status pane: the device viewer's live
volume estimate (volume, fill of the actuated area, covered area), as a
readings-grid row whose dropdown picks the readout shown, a tooltip listing
them all, and a button opening a non-modal Droplet Readouts window.

A pane's model mixes in DropletReadoutsModelMixin, its controller
DropletReadoutsControllerMixin, its grid takes droplet_readout_items(), and
its message handler stores each DEVICE_VIEWER_VOLUME_ESTIMATE message on
``model.volume_estimate``.
"""

# Enthought library imports.
from traits.api import Button, Enum, HasTraits, Instance, Property, Str, observe
from traitsui.api import UI, Item, UItem, VGroup, View

# Microdrop package imports.
from device_viewer.consts import VolumeEstimateMessage

# Microdrop style imports.
from microdrop_style.icons.icons import ICON_OPEN_IN_NEW

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import (
    HoverScrollEnumEditor,
    HtmlLabelEditor,
    IconButtonEditor,
)

# Droplet readouts the readings grid can show; the tooltip and the dialog
# show them all.
VOLUME_READOUT = "Volume"
FILL_READOUT = "Fill"
COVERED_AREA_READOUT = "Covered area"
DROPLET_READOUTS = [VOLUME_READOUT, FILL_READOUT, COVERED_AREA_READOUT]


class DropletReadoutsModelMixin(HasTraits):
    """The droplet readouts' state and display strings."""

    #: The device viewer's live volume estimate; None until it publishes.
    volume_estimate = Instance(VolumeEstimateMessage)

    #: The droplet readout the readings grid shows; the rest are in its
    #: tooltip and the readouts dialog.
    droplet_readout = Enum(*DROPLET_READOUTS)

    #: Opens the non-modal dialog listing every droplet readout.
    show_droplet_readouts = Button()

    volume_display = Property(Str, observe="volume_estimate")

    fill_display = Property(Str, observe="volume_estimate")

    covered_area_display = Property(Str, observe="volume_estimate")

    #: Why there is no droplet estimate, or "" when there is one.
    volume_status_message = Property(Str, observe="volume_estimate")

    #: The picked droplet readout's value, for the readings grid.
    droplet_readout_display = Property(
        Str,
        observe="droplet_readout, volume_display, fill_display, covered_area_display",
    )

    #: Every droplet readout, for the readings grid's tooltip (rich text).
    droplet_readouts_tooltip = Property(
        Str,
        observe=(
            "volume_display, fill_display, covered_area_display, volume_status_message"
        ),
    )

    def _get_volume_status_message(self):
        if self.volume_estimate is None:
            return "No volume estimate from the device viewer yet."

        return self.volume_estimate.status_message

    def _get_volume_display(self):
        if self.volume_status_message:
            return "-"

        return f"{self.volume_estimate.volume_ul:.1f} µL"

    def _get_fill_display(self):
        if self.volume_status_message:
            return "-"

        return f"{self.volume_estimate.fill_fraction:.0%}"

    def _get_covered_area_display(self):
        if self.volume_status_message:
            return "-"

        return f"{self.volume_estimate.covered_area_mm2:.1f} mm²"

    def _get_droplet_readout_display(self):
        displays = {
            VOLUME_READOUT: self.volume_display,
            FILL_READOUT: self.fill_display,
            COVERED_AREA_READOUT: self.covered_area_display,
        }

        return displays[self.droplet_readout]

    def _get_droplet_readouts_tooltip(self):
        lines = self._droplet_readout_lines()

        if self.volume_status_message:
            lines.append(self.volume_status_message)

        return "<br>".join(lines)

    def _droplet_readout_lines(self):
        """The tooltip's readout lines; a pane adds its own readings."""
        return [
            f"{VOLUME_READOUT}: {self.volume_display}",
            f"{FILL_READOUT}: {self.fill_display} of actuated area",
            f"{COVERED_AREA_READOUT}: {self.covered_area_display}",
        ]


def droplet_readout_items():
    """The readings grid's droplet readout row, for a three-column grid of
    label | value | control: the readout dropdown in the label column, its
    value (all readouts on hover), and the button opening the dialog."""
    return [
        UItem(
            "droplet_readout",
            editor=HoverScrollEnumEditor(values=DROPLET_READOUTS),
            width=120,
            tooltip="Droplet readout to show; hover the value for all of them",
        ),
        UItem(
            "droplet_readout_display",
            editor=HtmlLabelEditor(
                word_wrap=False, tooltip_name="droplet_readouts_tooltip"
            ),
        ),
        UItem(
            "show_droplet_readouts",
            editor=IconButtonEditor(
                glyph=ICON_OPEN_IN_NEW, tooltip="Show all droplet readouts"
            ),
        ),
    ]


#: Non-modal dialog with every droplet readout.
droplet_readouts_view = View(
    VGroup(
        Item("volume_display", style="readonly", label=VOLUME_READOUT),
        Item("fill_display", style="readonly", label=FILL_READOUT),
        Item("covered_area_display", style="readonly", label=COVERED_AREA_READOUT),
        UItem(
            "volume_status_message",
            style="readonly",
            visible_when="volume_status_message",
        ),
    ),
    title="Droplet Readouts",
    resizable=True,
)


class DropletReadoutsControllerMixin(HasTraits):
    """Opens the droplet readouts dialog for a status pane's controller (a
    TraitsUI Handler whose ``model`` mixes in DropletReadoutsModelMixin)."""

    #: The dialog's view; a pane with readings of its own overrides it.
    droplet_readouts_view = Instance(View)

    #: The open droplet readouts dialog, if any.
    _droplet_readouts_ui = Instance(UI)

    def _droplet_readouts_view_default(self):
        return droplet_readouts_view

    @observe("model:show_droplet_readouts")
    def _open_droplet_readouts(self, event):
        """Show every droplet readout in a non-modal window, raising the one
        already open instead of stacking another."""

        if self._droplet_readouts_ui is not None and self._droplet_readouts_ui.control:
            self._droplet_readouts_ui.control.raise_()
            self._droplet_readouts_ui.control.activateWindow()

            return

        parent = self.info.ui.control if self.info and self.info.ui else None
        self._droplet_readouts_ui = self.model.edit_traits(
            view=self.droplet_readouts_view, kind="live", parent=parent
        )
