# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A layer's own top-level ``<g>`` in the device SVG file (#650)."""

# Enthought library imports.
from traits.api import Interface, Str


class ISvgLayerCodec(Interface):
    """Read and write the one SVG layer group a device viewer layer owns.

    Groups no attached codec claims are kept in the file untouched, so a
    device saved without a layer's plugin keeps that layer's data.
    """

    #: ``inkscape:label`` of the top-level ``<g>`` this codec owns
    #: (e.g. "Zones").
    label = Str()

    def parse(self, group_element):
        """Return this layer's payload read from its ``<g>`` element."""

    def build(self, payload):
        """Return the ``<g>`` element for ``payload``, or None to omit it."""
