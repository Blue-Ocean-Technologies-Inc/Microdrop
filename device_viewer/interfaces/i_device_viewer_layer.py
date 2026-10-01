# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The device viewer layer contract (#650)."""

# Enthought library imports.
from traits.api import Instance, Int, Interface, List, Str

# Local imports.
from .descriptors import AlphaEntry, InteractionMode
from .i_interaction_handler import IInteractionHandler
from .i_svg_layer_codec import ISvgLayerCodec


class IDeviceViewerLayer(Interface):
    """One contribution to the device viewer pane.

    A layer bundles what one feature adds to the pane — a model manager,
    scene items, a sidebar section, opacity rows, interaction modes, an SVG
    layer — under one lifecycle, so the pane can mount it and tear it down
    as a unit on a hot load or unload. Every facet but ``id`` is optional;
    subclass ``BaseDeviceViewerLayer`` and implement only what is needed.

    Plugins contribute zero-arg factories returning a layer to the
    ``DEVICE_VIEWER_LAYERS`` extension point, and the pane builds one layer
    per attach. Every hook runs on the GUI thread.
    """

    #: Stable id ("zones", "gamepad"); one layer per id is attached.
    id = Str()

    #: Order of the layer's sidebar section after the built-in ones,
    #: lower first, ties broken by ``id``.
    priority = Int(50)

    #: Rows the layer adds to the layer-opacity table.
    alpha_entries = List(Instance(AlphaEntry))

    #: Values the layer adds to ``model.mode``.
    modes = List(Instance(InteractionMode))

    #: Behaviour for ``modes``; None for a layer without modes.
    interaction_handler = Instance(IInteractionHandler, allow_none=True)

    #: The layer's group in the device SVG; None if it stores nothing there.
    svg_codec = Instance(ISvgLayerCodec, allow_none=True)

    def attach(self, context):
        """Mount on a live pane: build managers, add scene items, start
        timers. ``context`` is the pane's ``LayerContext``."""

    def on_device_loaded(self, electrodes):
        """Rebuild per-device state for the device just loaded.

        ``electrodes`` is the main model's ``Electrodes``; its ``svg_model``
        holds the polygons, channel map and neighbours. Also called right
        after ``attach`` when a device is already loaded.
        """

    def detach(self):
        """Undo ``attach``: remove scene items, stop timers, drop observers.

        The base then removes the layer's sidebar section, opacity rows and
        modes itself, leaving a mode it owned first.
        """

    def build_sidebar_section(self, parent):
        """Return the layer's ``SidebarSection``, or None for no section.

        ``parent`` is the sidebar content widget the section joins.
        """

    def on_alpha_changed(self, key, opacity):
        """Repaint ``key``, one of ``alpha_entries``, at ``opacity``.

        ``opacity`` is in [0, 1] and already 0 when the row is hidden.
        """

    def contribute_state(self, payload):
        """Add this layer's fields to the outgoing state message ``payload``
        (a dict). Provisional: only the paths layer needs it."""

    def apply_state(self, message):
        """Apply an inbound ``DeviceViewerMessageModel``. Provisional: only
        the paths layer needs it."""
