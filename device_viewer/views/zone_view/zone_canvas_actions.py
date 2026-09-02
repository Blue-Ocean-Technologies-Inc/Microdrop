# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Floating action strips and region context menu for the zone tools —
a Qt-aware view helper kept out of the interaction service so the service
stays free of overlay/menu bookkeeping."""

# Enthought library imports.
from pyface.qt.QtWidgets import QGraphicsView, QMenu
from traits.api import HasTraits, Instance, observe

# Microdrop package imports.
from device_viewer.consts import ZONE_DRAW_MODE, ZONE_SELECT_MODE
from device_viewer.models.main_model import DeviceViewMainModel
from device_viewer.views.electrode_view.electrode_layer import ElectrodeLayer

# Microdrop style imports.
from microdrop_style.icons.icons import (
    ICON_CHECK,
    ICON_CLOSE,
    ICON_DELETE,
    ICON_EDIT,
    ICON_VISIBILITY_OFF,
)

# Local imports.
from .zone_overlay import ZoneOverlayStrip

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class ZoneCanvasActions(HasTraits):
    """Owns the two floating overlay strips and the region context menu,
    anchoring them beside a pending selection / selected region on the
    device view and keeping them parked there as the view scrolls or
    resizes.

    The strips' button callbacks set the same ``model.zones`` Button
    traits the sidebar buttons set, so both entry points flow through the
    manager's normal command handling.
    """

    #: Device view model — source of the zone manager (``model.zones``).
    model = Instance(DeviceViewMainModel)

    #: The QGraphicsView showing the device, and the anchor for overlays.
    device_view = Instance(QGraphicsView)

    #: The current electrode layer view — source of the zone scene items
    #: (``zone_items``, ``zone_pending_item``) the strips anchor beside.
    electrode_view_layer = Instance(ElectrodeLayer)

    #: Strip shown beside a pending (uncommitted) zone selection.
    _commit_overlay = Instance(ZoneOverlayStrip, allow_none=True)

    #: Strip shown beside a selected, already-committed region.
    _selection_overlay = Instance(ZoneOverlayStrip, allow_none=True)

    #: Keeps the region context menu alive while it is open.
    _context_menu = Instance(QMenu, allow_none=True)

    def traits_init(self):
        self.device_view.viewport_changed.connect(self.reposition)

    @observe("model.zones.show_canvas_overlays")
    def _on_show_canvas_overlays_changed(self, event):
        self.reposition()

    def _ensure_overlays(self):
        if self._commit_overlay is not None:
            return
        manager = self.model.zones
        viewport = self.device_view.viewport()
        self._commit_overlay = ZoneOverlayStrip(
            viewport,
            [
                (
                    ICON_CHECK,
                    "Commit zone",
                    lambda: setattr(manager, "commit_button", True),
                ),
                (
                    ICON_DELETE,
                    "Discard selection",
                    lambda: setattr(manager, "clear_pending_button", True),
                ),
                (
                    ICON_CLOSE,
                    "Hide these buttons",
                    lambda: setattr(manager, "show_canvas_overlays", False),
                ),
            ],
        )
        self._selection_overlay = ZoneOverlayStrip(
            viewport,
            [
                (
                    ICON_EDIT,
                    "Edit region",
                    lambda: setattr(manager, "edit_region_button", True),
                ),
                (
                    ICON_DELETE,
                    "Delete region",
                    lambda: setattr(manager, "delete_region_button", True),
                ),
                (
                    ICON_VISIBILITY_OFF,
                    "Hide region",
                    lambda: setattr(manager, "hide_region_button", True),
                ),
                (
                    ICON_CLOSE,
                    "Hide these buttons",
                    lambda: setattr(manager, "show_canvas_overlays", False),
                ),
            ],
        )

    def reposition(self):
        """Show each strip by its anchor item when its situation applies,
        hide it otherwise. Safe to call before a scene/layer exists."""
        if self.electrode_view_layer is None:
            return
        self._ensure_overlays()
        manager = self.model.zones
        layer = self.electrode_view_layer
        show = manager.show_canvas_overlays

        pending_item = layer.zone_pending_item
        if show and self.model.mode == ZONE_DRAW_MODE and pending_item is not None:
            self._commit_overlay.place_at(
                self.device_view, pending_item.sceneBoundingRect().topRight()
            )
        else:
            self._commit_overlay.hide()

        selected = manager.selected_region
        selected_item = layer.zone_items.get(selected.id) if selected else None
        if show and self.model.mode == ZONE_SELECT_MODE and selected_item is not None:
            self._selection_overlay.place_at(
                self.device_view, selected_item.sceneBoundingRect().topRight()
            )
        else:
            self._selection_overlay.hide()

    def show_context_menu(self, region, screen_pos):
        manager = self.model.zones
        self._context_menu = QMenu()
        self._context_menu.addAction(
            "Edit region", lambda: self._begin_region_edit(region)
        )
        change_type_menu = self._context_menu.addMenu("Change type")
        for zone_type in manager.zone_types:
            if zone_type.id == region.zone_id:
                continue
            change_type_menu.addAction(
                zone_type.name,
                lambda zone_id=zone_type.id: manager.change_region_zone(
                    region, zone_id
                ),
            )
        self._context_menu.addAction(
            "Delete region", lambda: manager.remove_region(region)
        )
        self._context_menu.popup(screen_pos)

    def _begin_region_edit(self, region):
        # Selecting first lets the Edit button flow (ZonesController) do the
        # mode switch exactly as the sidebar button does.
        self.model.zones.selected_region = region
        self.model.zones.edit_region_button = True

    def dispose(self):
        """Disconnect the view signal and release the strips."""
        try:
            self.device_view.viewport_changed.disconnect(self.reposition)
        except (RuntimeError, TypeError):
            # Already disconnected, or the C++ view is already gone.
            logger.debug("viewport_changed disconnect failed", exc_info=True)
        for overlay in (self._commit_overlay, self._selection_overlay):
            if overlay is not None:
                overlay.hide()
                overlay.deleteLater()
        self._commit_overlay = None
        self._selection_overlay = None
