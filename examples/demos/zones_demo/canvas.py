# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The one deliberately-Qt piece of the demo: the device canvas.

A QGraphicsView has no stock TraitsUI equivalent, so this widget owns all
scene painting and mouse interaction; the TraitsUI view embeds it through a
``CustomEditor``. Zone regions and the pending-selection highlight use the
shipped scene items (device_viewer.views.zone_view.zone_region_item), drawn
in raw SVG coordinates (scale 1.0) since the demo has no separate view scale.
Everything is driven by ``ZonesDemoModel``/``ZoneLayerManager`` traits via the
Qt-free ``_CanvasRedrawBridge`` observers.
"""

# Enthought library imports.
from pyface.qt.QtCore import QRectF, Qt
from pyface.qt.QtGui import (
    QBrush,
    QColor,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QShortcut,
)
from pyface.qt.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QMenu,
)
from traits.api import Callable, HasTraits, Instance, observe

# Microdrop package imports.
from device_viewer.consts import (
    ZONE_CLICK_DRAG_THRESHOLD_PX,
    ZONE_DRAW_MODE,
    ZONE_OUTLINE_PEN_WIDTH,
    ZONE_SELECT_MODE,
    ZONE_SELECTED_OUTLINE_PEN_WIDTH,
    ZONE_SUBTRACT_PREVIEW_COLOR,
)
from device_viewer.views.zone_view.zone_overlay import ZoneOverlayStrip
from device_viewer.views.zone_view.zone_region_item import (
    ZoneRegionItem,
    make_selection_highlight_item,
    shapely_geometry_to_painter_path,
)

# Microdrop style imports.
from microdrop_style.icons.icons import (
    ICON_CHECK,
    ICON_CLOSE,
    ICON_DELETE,
    ICON_EDIT,
    ICON_VISIBILITY_OFF,
)

# Local imports.
from .consts import ELECTRODE_FILL_COLOR, ELECTRODE_Z_VALUE
from .models import ZonesDemoModel

# Live rubber-band capture preview and the region-drag ghost draw above
# committed regions and the pending-selection highlight (which the shipped
# ZoneRegionItem/make_selection_highlight_item place at 0.5/0.6).
DEMO_BAND_Z_VALUE = 0.7


class _CanvasRedrawBridge(HasTraits):
    """Qt-free observer wiring: model/manager changes -> canvas callbacks."""

    model = Instance(ZonesDemoModel)

    redraw_zones = Callable
    redraw_pending_selection = Callable
    apply_mode = Callable
    rebuild_electrodes = Callable

    @observe(
        "[model:manager:regions, model:manager:regions.items, "
        "model:manager:regions:items:electrode_ids.items, "
        "model:manager:regions:items:visible, "
        "model:manager:selected_region, model:manager:selected_regions.items, "
        "model:manager:editing_region, "
        "model:manager:zone_types.items, model:manager:zone_types:items:color, "
        "model:manager:regions:items:zone_id]"
    )
    def _zones_changed(self, event):
        self.redraw_zones()

    @observe(
        "[model:manager:pending_electrode_ids, "
        "model:manager:pending_electrode_ids.items, "
        "model:manager:active_zone_id]"
    )
    def _pending_selection_changed(self, event):
        self.redraw_pending_selection()

    @observe("[model:mode, model:manager:show_canvas_overlays]")
    def _mode_changed(self, event):
        self.apply_mode()

    @observe("model:manager:electrode_polygons")
    def _device_changed(self, event):
        self.rebuild_electrodes()


class ZonesCanvas(QGraphicsView):
    """Device view with a pan mode, a zone-draw (rubber band) mode, and a
    select mode for picking existing regions."""

    def __init__(self, model: ZonesDemoModel, parent=None):
        super().__init__(parent)
        # Parent the scene to the view so Qt keeps it alive.
        self.setScene(QGraphicsScene(self))
        self.model = model
        self.manager = model.manager
        self._zone_region_items = []
        self._pending_selection_item = None
        self._drag_preview_item = None
        self._pending_rubber_band_scene_rect = None
        self._press_view_pos = None
        self._context_menu = None
        # Select-mode region dragging: the item under the press, the ghost
        # outline that follows the cursor, and the press position in scene
        # coords the drop delta is measured from.
        self._drag_region_item = None
        self._drag_ghost_item = None
        self._drag_start_scene_pos = None
        # Ctrl+drag in draw mode subtracts the swept electrodes from the
        # pending selection instead of adding them.
        self._band_subtracts = False

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        #: Top-level window this canvas watches for Escape (installed lazily
        #: in showEvent — the CustomEditor reparents the canvas after
        #: construction, so the window isn't known yet here).
        self._escape_window = None
        self.rubberBandChanged.connect(self._on_rubber_band_changed)
        self._commit_overlay = self._build_commit_overlay()
        self._selection_overlay = self._build_selection_overlay()
        self._bridge = _CanvasRedrawBridge(
            model=model,
            redraw_zones=self._redraw_zone_items,
            redraw_pending_selection=self._redraw_pending_selection,
            apply_mode=self._apply_mode,
            rebuild_electrodes=self._rebuild_electrodes,
        )
        self._rebuild_electrodes()
        self._apply_mode()

    # -------------------------------------------------------------- overlays
    # Floating button strips over the viewport, the shipped
    # device_viewer.views.zone_view.zone_overlay.ZoneOverlayStrip. They only
    # FIRE the shipped manager's Button traits — the behavior stays in the
    # Qt-free controller, exactly as if the matching sidebar button had been
    # clicked.
    def _build_commit_overlay(self):
        """Check/delete/dismiss buttons shown while a pending selection
        exists: check commits it, delete discards it, dismiss hides the
        strip so the selection can keep being edited (it returns on the
        next selection change)."""
        return ZoneOverlayStrip(
            self.viewport(),
            [
                (
                    ICON_CHECK,
                    "Commit the selection as a zone region",
                    lambda: setattr(self.manager, "commit_button", True),
                ),
                (
                    ICON_DELETE,
                    "Clear the selection without committing",
                    lambda: setattr(self.manager, "clear_pending_button", True),
                ),
                (
                    ICON_CLOSE,
                    (
                        "Dismiss the canvas buttons — every action is also "
                        "in the sidebar; re-enable them there"
                    ),
                    lambda: setattr(self.manager, "show_canvas_overlays", False),
                ),
            ],
        )

    def _build_selection_overlay(self):
        """Edit/delete/hide buttons pinned to the selected region."""
        return ZoneOverlayStrip(
            self.viewport(),
            [
                (
                    ICON_EDIT,
                    "Edit the selected region's electrodes",
                    lambda: setattr(self.manager, "edit_region_button", True),
                ),
                (
                    ICON_DELETE,
                    "Delete the selected region",
                    lambda: setattr(self.manager, "delete_region_button", True),
                ),
                (
                    ICON_VISIBILITY_OFF,
                    "Hide the selected region (re-show it via the regions table)",
                    lambda: setattr(self.manager, "hide_region_button", True),
                ),
                (
                    ICON_CLOSE,
                    (
                        "Dismiss the canvas buttons — every action is also "
                        "in the sidebar; re-enable them there"
                    ),
                    lambda: setattr(self.manager, "show_canvas_overlays", False),
                ),
            ],
        )

    # ------------------------------------------------------------------ mode
    def _apply_mode(self):
        # The floating button sets are mode-gated (commit set in draw,
        # selection set in select, one at a time) — re-evaluate both so
        # leaving a mode clears its buttons.
        self._redraw_pending_selection()
        self._redraw_zone_items()
        if self.model.mode == ZONE_DRAW_MODE:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        elif self.model.mode == ZONE_SELECT_MODE:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        else:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

    # ---------------------------------------------------------------- device
    def _rebuild_electrodes(self):
        self.scene().clear()
        self._zone_region_items = []
        self._pending_selection_item = None
        self._drag_preview_item = None
        for polygon in self.manager.electrode_polygons.values():
            electrode_item = QGraphicsPathItem(
                shapely_geometry_to_painter_path(polygon, 1.0)
            )
            electrode_item.setBrush(QBrush(QColor(ELECTRODE_FILL_COLOR)))
            electrode_item.setPen(QPen(Qt.PenStyle.NoPen))
            electrode_item.setZValue(ELECTRODE_Z_VALUE)
            self.scene().addItem(electrode_item)
        self.scene().setSceneRect(self.scene().itemsBoundingRect())
        self.resetTransform()
        self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    # ----------------------------------------------------------- interaction
    def _on_rubber_band_changed(self, viewport_rect, from_scene_point, to_scene_point):
        if not viewport_rect.isNull():
            self._pending_rubber_band_scene_rect = QRectF(
                from_scene_point, to_scene_point
            ).normalized()
            if self.model.mode == ZONE_DRAW_MODE:
                self._preview_rubber_band(self._pending_rubber_band_scene_rect)
        elif self._pending_rubber_band_scene_rect is not None:
            committed_rect = self._pending_rubber_band_scene_rect
            self._pending_rubber_band_scene_rect = None
            if self.model.mode == ZONE_DRAW_MODE:
                self._clear_drag_preview()
                captured_ids = self.manager.capture_electrode_ids_touching(
                    committed_rect.left(),
                    committed_rect.top(),
                    committed_rect.right(),
                    committed_rect.bottom(),
                )
                if self._band_subtracts:
                    self.manager.remove_from_pending(captured_ids)
                else:
                    self.manager.add_to_pending(captured_ids)
            elif self.model.mode == ZONE_SELECT_MODE:
                captured = set(
                    self.manager.capture_electrode_ids_touching(
                        committed_rect.left(),
                        committed_rect.top(),
                        committed_rect.right(),
                        committed_rect.bottom(),
                    )
                )
                self.manager.selected_regions = [
                    region
                    for region in self.manager.regions
                    if region.visible and captured & set(region.electrode_ids)
                ]

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_view_pos = event.pos()
            # Ctrl+drag in draw mode sweeps electrodes OUT of the pending
            # selection; in select mode ctrl is the multi-select gesture
            # instead, so the two never clash.
            self._band_subtracts = (
                bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                and self.model.mode == ZONE_DRAW_MODE
            )
            # Ctrl is the multi-select gesture — never a drag.
            if self.model.mode == ZONE_SELECT_MODE and not (
                event.modifiers() & Qt.KeyboardModifier.ControlModifier
            ):
                self._drag_region_item = next(
                    (
                        item
                        for item in self.items(event.pos())
                        if isinstance(item, ZoneRegionItem)
                    ),
                    None,
                )
                self._drag_start_scene_pos = self.mapToScene(event.pos())
                if self._drag_region_item is None:
                    # Empty space: start a rubber band to multi-select
                    # regions instead of a region drag.
                    self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._drag_region_item is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and (event.pos() - self._press_view_pos).manhattanLength()
            >= ZONE_CLICK_DRAG_THRESHOLD_PX
        ):
            if self._drag_ghost_item is None:
                # Dragging a member of a multi-selection moves the whole
                # group; the ghost previews their combined footprint.
                pressed_region = self._drag_region_item.region
                selection = self.manager.selected_regions
                if pressed_region in selection and len(selection) > 1:
                    ghost_path = QPainterPath()
                    for item in self._zone_region_items:
                        if item.region in selection:
                            ghost_path.addPath(item.path())
                else:
                    ghost_path = self._drag_region_item.path()
                ghost = QGraphicsPathItem(ghost_path)
                ghost.setBrush(self._drag_region_item.brush())
                ghost_pen = QPen(self._drag_region_item.pen())
                ghost_pen.setStyle(Qt.PenStyle.DashLine)
                ghost.setPen(ghost_pen)
                ghost.setZValue(DEMO_BAND_Z_VALUE)
                self.scene().addItem(ghost)
                self._drag_ghost_item = ghost
            delta = self.mapToScene(event.pos()) - self._drag_start_scene_pos
            self._drag_ghost_item.setPos(delta)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._drag_ghost_item is not None
        ):
            # Region drag: drop snaps to the lattice (or back, if the shape
            # cannot land there); the moved region stays selected.
            self.scene().removeItem(self._drag_ghost_item)
            self._drag_ghost_item = None
            delta = self.mapToScene(event.pos()) - self._drag_start_scene_pos
            region = self._drag_region_item.region
            self._drag_region_item = None
            selection = list(self.manager.selected_regions)
            if region in selection and len(selection) > 1:
                # Group move: keep the multi-selection, move it as one.
                self.manager.translate_regions(selection, delta.x(), delta.y())
            else:
                self.manager.selected_region = region
                self.manager.translate_regions([region], delta.x(), delta.y())
            self._press_view_pos = None
            return
        is_click = (
            event.button() == Qt.MouseButton.LeftButton
            and self._press_view_pos is not None
            and (event.pos() - self._press_view_pos).manhattanLength()
            < ZONE_CLICK_DRAG_THRESHOLD_PX
        )
        if is_click and self.model.mode == ZONE_DRAW_MODE:
            scene_pos = self.mapToScene(event.pos())
            electrode_id = self.manager.electrode_id_at(scene_pos.x(), scene_pos.y())
            if electrode_id is not None:
                self.manager.toggle_electrode_in_pending(electrode_id)
        elif is_click and self.model.mode == ZONE_SELECT_MODE:
            # Topmost region under the cursor, or None to deselect.
            clicked_region = next(
                (
                    item.region
                    for item in self.items(event.pos())
                    if isinstance(item, ZoneRegionItem)
                ),
                None,
            )
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.manager.toggle_region_in_selection(clicked_region)
            else:
                self.manager.selected_region = clicked_region
        self._press_view_pos = None
        self._drag_region_item = None
        if self.model.mode == ZONE_SELECT_MODE:
            # Fall back to NoDrag after a rubber-band multi-select — a press
            # on empty space temporarily switched into RubberBandDrag above.
            self._apply_mode()

    def mouseDoubleClickEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.model.mode == ZONE_SELECT_MODE
        ):
            region = next(
                (
                    item.region
                    for item in self.items(event.pos())
                    if isinstance(item, ZoneRegionItem)
                ),
                None,
            )
            if region is not None:
                self.manager.selected_region = region
                self.manager.edit_region_button = True
                return
        super().mouseDoubleClickEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self._escape_window is not self.window():
            self._escape_window = self.window()
            self._wire_escape_shortcut()

    def _wire_escape_shortcut(self):
        """TraitsUI's _StickyDialog owns a window-wide Escape QShortcut
        (that is how it swallows Escape so the dialog doesn't close). The
        shortcut map consumes the key BEFORE any KeyPress exists, so
        keyPressEvent / event filters never see it, and registering a
        second Escape shortcut makes the pair ambiguous — Qt then fires
        neither. Piggyback on the existing shortcut when there is one;
        otherwise register our own."""
        escape = QKeySequence(Qt.Key.Key_Escape)
        for shortcut in self._escape_window.findChildren(QShortcut):
            if shortcut.key() == escape:
                shortcut.activated.connect(self._handle_escape)
                return
        shortcut = QShortcut(escape, self._escape_window)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.activated.connect(self._handle_escape)

    def _handle_escape(self):
        if self._drag_ghost_item is not None:
            # Cancel the in-flight region drag: view-local state only.
            self.scene().removeItem(self._drag_ghost_item)
            self._drag_ghost_item = None
            self._drag_region_item = None
            return
        self.model.escape_pressed = True

    def wheelEvent(self, event):
        zoom_factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(zoom_factor, zoom_factor)

    def contextMenuEvent(self, event):
        for item in self.items(event.pos()):
            if isinstance(item, ZoneRegionItem):
                region = item.region
                self._context_menu = QMenu(self)
                edit_action = self._context_menu.addAction("Edit region")
                edit_action.triggered.connect(
                    lambda _checked=False: self._edit_region(region)
                )
                change_type_menu = self._context_menu.addMenu("Change type")
                for zone_type in self.manager.zone_types:
                    if zone_type.id == region.zone_id:
                        continue
                    action = change_type_menu.addAction(zone_type.name)
                    action.triggered.connect(
                        lambda _checked=False, zone_id=zone_type.id: (
                            self.manager.change_region_zone(region, zone_id)
                        )
                    )
                delete_action = self._context_menu.addAction("Delete region")
                delete_action.triggered.connect(
                    lambda _checked=False: self.manager.remove_region(region)
                )
                self._context_menu.popup(event.globalPos())
                return
        super().contextMenuEvent(event)

    def _edit_region(self, region):
        # Select first — the edit flow (and its mode gate) acts on the
        # selected region, same as the overlay/sidebar Edit buttons.
        self.manager.selected_region = region
        self.manager.edit_region_button = True

    # -------------------------------------------------------------- painting
    def _make_selection_highlight_item(self, electrode_ids, color=None):
        """Dashed highlight over the given electrodes in ``color`` (defaults
        to the active zone type's color), or None when there is nothing to
        show."""
        if color is None:
            zone_type = self.manager.zone_type_for(self.manager.active_zone_id)
            if zone_type is None:
                return None
            color = zone_type.color
        geometry = self.manager.electrode_union(electrode_ids)
        if geometry is None:
            return None
        return make_selection_highlight_item(geometry, 1.0, color)

    def _preview_rubber_band(self, preview_rect):
        """Live drag feedback: highlight the electrodes the rubber band would
        add to (or, ctrl-held, subtract from) the pending selection."""
        self._clear_drag_preview()
        self._drag_preview_item = self._make_selection_highlight_item(
            self.manager.capture_electrode_ids_touching(
                preview_rect.left(),
                preview_rect.top(),
                preview_rect.right(),
                preview_rect.bottom(),
            ),
            color=ZONE_SUBTRACT_PREVIEW_COLOR if self._band_subtracts else None,
        )
        if self._drag_preview_item is not None:
            self.scene().addItem(self._drag_preview_item)

    def _clear_drag_preview(self):
        if self._drag_preview_item is not None:
            self.scene().removeItem(self._drag_preview_item)
            self._drag_preview_item = None

    def _redraw_pending_selection(self):
        if self._pending_selection_item is not None:
            self.scene().removeItem(self._pending_selection_item)
            self._pending_selection_item = None
        self._pending_selection_item = self._make_selection_highlight_item(
            self.manager.pending_electrode_ids
        )
        if self._pending_selection_item is not None:
            self.scene().addItem(self._pending_selection_item)
        # The commit buttons belong to draw mode only.
        if (
            self._pending_selection_item is not None
            and self.manager.show_canvas_overlays
            and self.model.mode == ZONE_DRAW_MODE
        ):
            self._commit_overlay.place_at(
                self, self._pending_selection_item.sceneBoundingRect().topRight()
            )
        else:
            self._commit_overlay.hide()

    def _redraw_zone_items(self):
        for item in self._zone_region_items:
            self.scene().removeItem(item)
        self._zone_region_items = []
        selected_region_item = None
        for region in self.manager.regions:
            if not region.visible or region is self.manager.editing_region:
                continue
            zone_type = self.manager.zone_type_for(region.zone_id)
            outline_geometry = self.manager.region_outline(region)
            if zone_type is None or outline_geometry is None:
                continue
            is_selected = (
                region is self.manager.selected_region
                or region in self.manager.selected_regions
            )
            region_item = ZoneRegionItem(
                region,
                outline_geometry,
                1.0,
                zone_type.color,
                1.0,
                outline_pen_width=(
                    ZONE_SELECTED_OUTLINE_PEN_WIDTH
                    if is_selected
                    else ZONE_OUTLINE_PEN_WIDTH
                ),
            )
            self.scene().addItem(region_item)
            self._zone_region_items.append(region_item)
            if is_selected:
                selected_region_item = region_item
        # The edit/delete/hide buttons belong to select mode only.
        if (
            selected_region_item is not None
            and self.manager.show_canvas_overlays
            and self.model.mode == ZONE_SELECT_MODE
        ):
            self._selection_overlay.place_at(
                self, selected_region_item.sceneBoundingRect().topRight()
            )
        else:
            self._selection_overlay.hide()


def zones_canvas_factory(parent, editor):
    """``CustomEditor`` widget factory: the edited object is the demo model.
    ``parent`` is the enclosing layout (TraitsUI adds the widget to it), so
    the canvas is created parentless."""
    return ZonesCanvas(editor.object)
