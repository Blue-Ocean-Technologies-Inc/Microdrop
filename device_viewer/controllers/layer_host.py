# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Mount the layers sibling plugins contribute on a device viewer pane."""

# Enthought library imports.
from pyface.qt.QtCore import QCoreApplication, QThread
from pyface.qt.QtWidgets import QScrollArea
from traits.api import Any, Dict, HasTraits, Instance, List, Str, observe

# Local imports.
from ..consts import LAYER_CONTRACT_VERSION
from ..interfaces.descriptors import SidebarSection
from ..interfaces.i_device_viewer_layer import IDeviceViewerLayer
from ..interfaces.layer_context import LayerContext
from ..views.sidebar.host import insert_section_box, remove_section_box

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _sort_key(layer):
    return (layer.priority, layer.id)


class LayerHost(HasTraits):
    """Attach, order and detach the device viewer layers of one pane.

    Contributions are zero-arg factories, not layer instances: a layer holds
    the state of the pane it is attached to (managers, scene items, its
    sidebar widgets), so each attach builds a fresh one and a detached layer
    is simply dropped — never re-attached with stale state. A factory also
    lets a broken plugin fail at build time, where the host logs and skips
    it, and keeps a layer's heavy imports out of the process until a pane
    mounts it (the ``CAMERA_SOURCES`` precedent).

    With no layers contributed the host changes nothing on the pane.
    """

    #: Handed to every layer on attach; the host keeps ``stepping`` current.
    context = Instance(LayerContext)

    #: The pane's sidebar; layer sections go below the built-in ones. None
    #: leaves layers without a sidebar (headless use).
    sidebar = Instance(QScrollArea)

    #: Attached layers in (priority, id) order.
    layers = List(Instance(IDeviceViewerLayer))

    #: The attached layer built by each contributed factory.
    _layers_by_factory = Dict(Any, Instance(IDeviceViewerLayer))

    #: Each attached layer's sidebar section and its box in the sidebar,
    #: by layer id; holding the section keeps its widgets' owners alive.
    _sections = Dict(Str, Instance(SidebarSection))
    _section_boxes = Dict(Str, Any)

    #: The layer that added each opacity-table row and mode, by key / id.
    _alpha_owners = Dict(Str, Instance(IDeviceViewerLayer))
    _mode_owners = Dict(Str, Instance(IDeviceViewerLayer))

    # ------------------------------------------------------------------ #
    # Contribution changes                                                 #
    # ------------------------------------------------------------------ #

    def add_layers(self, factories):
        """Build a layer from each factory and attach it.

        A layer whose id is already attached is dropped (first wins), as is
        a factory or layer that fails; both are logged.
        """
        self._check_gui_thread()
        built = []

        for factory in factories:
            layer = self._build_layer(factory)

            if layer is None:
                continue

            taken = {other.id for other in self.layers}
            taken.update(other.id for _, other in built)

            if layer.id in taken:
                logger.warning(
                    f"Device viewer layer {layer.id!r} from {factory!r} dropped: "
                    f"a layer with that id is already attached"
                )
                continue

            built.append((factory, layer))

        for factory, layer in sorted(built, key=lambda pair: _sort_key(pair[1])):
            if self._attach(layer):
                self._layers_by_factory[factory] = layer

    def remove_layers(self, factories):
        """Detach the layers the given factories built."""
        self._check_gui_thread()

        for factory in factories:
            layer = self._layers_by_factory.pop(factory, None)

            if layer is not None:
                self._detach(layer)

    def apply_change(self, added, removed):
        """Apply a change of the contributed factories: removals first."""
        self.remove_layers(removed)
        self.add_layers(added)

    def remove_all(self):
        """Detach every layer, e.g. when the pane closes."""
        self.remove_layers(list(self._layers_by_factory))

    # ------------------------------------------------------------------ #
    # Fan-out to the attached layers                                       #
    # ------------------------------------------------------------------ #

    def device_loaded(self, stepping):
        """Tell every layer a new device is in place.

        ``stepping`` is the electrode cursor built for the new device.
        """
        self._check_gui_thread()
        self.context.stepping = stepping

        for layer in self.layers:
            self._call(layer, "on_device_loaded", self.context.model.electrodes)

    # ------------------------------------------------------------------ #
    # Attach / detach                                                      #
    # ------------------------------------------------------------------ #

    def _build_layer(self, factory):
        try:
            layer = factory()
        except Exception:
            logger.error(
                f"Device viewer layer factory {factory!r} failed; skipping",
                exc_info=True,
            )
            return None

        if not isinstance(layer, IDeviceViewerLayer):
            logger.error(
                f"Device viewer layer factory {factory!r} returned {layer!r}, "
                f"which does not provide IDeviceViewerLayer; skipping"
            )
            return None

        return layer

    def _attach(self, layer):
        """Mount one layer; return whether it is now attached."""
        self._warn_on_contract_mismatch(layer)

        try:
            layer.attach(self.context)
        except Exception:
            logger.error(
                f"Device viewer layer {layer.id!r} failed to attach; skipping",
                exc_info=True,
            )
            return False

        position = sum(_sort_key(other) <= _sort_key(layer) for other in self.layers)
        self.layers.insert(position, layer)

        self._add_section(layer)
        self._add_alpha_rows(layer)
        self._add_modes(layer)

        if self.context.model.electrodes.svg_model is not None:
            self._call(layer, "on_device_loaded", self.context.model.electrodes)

        logger.info(f"Device viewer layer {layer.id!r} attached")

        return True

    def _detach(self, layer):
        # Leave the layer's modes while it can still clean up after them.
        self._remove_modes(layer)
        self._call(layer, "detach")
        self._remove_section(layer)
        self._remove_alpha_rows(layer)

        self.layers.remove(layer)

        logger.info(f"Device viewer layer {layer.id!r} detached")

    def _add_section(self, layer):
        if self.sidebar is None:
            return

        section = self._call(layer, "build_sidebar_section", self.sidebar.widget())

        if section is None:
            return

        # Above the next attached layer that has a box, else last.
        later_boxes = [
            self._section_boxes[other.id]
            for other in self.layers[self.layers.index(layer) + 1 :]
            if other.id in self._section_boxes
        ]
        before = later_boxes[0] if later_boxes else None

        self._sections[layer.id] = section
        self._section_boxes[layer.id] = insert_section_box(
            self.sidebar, section, before=before
        )

    def _remove_section(self, layer):
        box = self._section_boxes.pop(layer.id, None)
        self._sections.pop(layer.id, None)

        if box is not None:
            remove_section_box(self.sidebar, box)

    def _add_alpha_rows(self, layer):
        model = self.context.model

        for entry in layer.alpha_entries:
            if any(row.key == entry.key for row in model.alpha_map):
                logger.warning(
                    f"Device viewer layer {layer.id!r}: opacity row "
                    f"{entry.key!r} already exists; not added"
                )
                continue

            model.add_alpha_row(entry.key, entry.alpha, entry.visible)
            self._alpha_owners[entry.key] = layer

    def _remove_alpha_rows(self, layer):
        for key in self._owned(self._alpha_owners, layer):
            del self._alpha_owners[key]
            self.context.model.remove_alpha_row(key)

    def _add_modes(self, layer):
        model = self.context.model

        for mode in layer.modes:
            if mode.id in model.available_modes:
                logger.warning(
                    f"Device viewer layer {layer.id!r}: mode {mode.id!r} "
                    f"already exists; not added"
                )
                continue

            model.add_mode(mode.id)
            self._mode_owners[mode.id] = layer

    def _remove_modes(self, layer):
        for mode_id in self._owned(self._mode_owners, layer):
            # Leave the mode while its owner still answers for it.
            self.context.model.remove_mode(mode_id)
            del self._mode_owners[mode_id]

    # ------------------------------------------------------------------ #
    # Model observers                                                      #
    # ------------------------------------------------------------------ #

    @observe("context:model:mode")
    def _dispatch_mode_change(self, event):
        old_owner = self._mode_owners.get(event.old)
        new_owner = self._mode_owners.get(event.new)

        if old_owner is not None:
            self._show_mode_status(old_owner, event.old, show=False)

            if old_owner.interaction_handler is not None:
                self._call(
                    old_owner.interaction_handler, "on_exit", event.old, event.new
                )

        if new_owner is not None:
            if new_owner.interaction_handler is not None:
                self._call(
                    new_owner.interaction_handler, "on_enter", event.new, event.old
                )

            self._show_mode_status(new_owner, event.new, show=True)

    @observe("context:model:alpha_map:items:[alpha, visible]")
    def _dispatch_alpha_change(self, event):
        key = event.object.key
        owner = self._alpha_owners.get(key)

        if owner is not None:
            self._call(
                owner, "on_alpha_changed", key, self.context.model.get_alpha(key)
            )

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _show_mode_status(self, layer, mode_id, show):
        """Show or clear the status-bar hint of one of ``layer``'s modes."""
        status_bar_manager = self.context.status_bar_manager
        mode = next((mode for mode in layer.modes if mode.id == mode_id), None)

        if status_bar_manager is None or mode is None or not mode.status_message:
            return

        if show:
            status_bar_manager.messages += [mode.status_message]
        elif mode.status_message in status_bar_manager.messages:
            status_bar_manager.remove(mode.status_message)

    @staticmethod
    def _owned(owners, layer):
        return [key for key, owner in owners.items() if owner is layer]

    @staticmethod
    def _warn_on_contract_mismatch(layer):
        """Log a layer built against another contract; it mounts regardless."""
        if layer.contract_version == LAYER_CONTRACT_VERSION:
            return

        built_against = layer.contract_version or "an undeclared version"

        logger.warning(
            f"Device viewer layer {layer.id!r} was built against layer contract "
            f"{built_against}; this Microdrop provides {LAYER_CONTRACT_VERSION}. "
            f"Mounting it anyway."
        )

    @staticmethod
    def _call(target, hook, *args):
        """Run one layer hook; a failing layer is logged, never fatal."""
        try:
            return getattr(target, hook)(*args)
        except Exception:
            logger.error(
                f"Device viewer layer hook {target!r}.{hook} failed", exc_info=True
            )
            return None

    @staticmethod
    def _check_gui_thread():
        """Log loudly when a layer change arrives off the GUI thread."""
        application = QCoreApplication.instance()

        if (
            application is not None
            and QThread.currentThread() is not application.thread()
        ):
            logger.error(
                "Device viewer layers changed off the GUI thread; hop to it "
                "first (invoke_later) — layers own Qt widgets and scene items",
                stack_info=True,
            )
