# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""ZoneProtocolControlsPlugin — contributes the Zone Target compound column
(#965) to the pluggable protocol tree.

Loaded as part of FRONTEND_PLUGINS in examples/plugin_consts.py.
"""

# Enthought library imports.
from envisage.api import Plugin
from traits.api import Instance, List

# Microdrop package imports.
from pluggable_protocol_tree.consts import PROTOCOL_COLUMNS
from pluggable_protocol_tree.interfaces.i_compound_column import ICompoundColumn

# Local imports.
from .consts import PKG, PKG_name
from .protocol_columns import make_zone_target_column


class ZoneProtocolControlsPlugin(Plugin):
    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    contributed_protocol_columns = List(
        Instance(ICompoundColumn), contributes_to=PROTOCOL_COLUMNS
    )

    def _contributed_protocol_columns_default(self):
        return [make_zone_target_column()]
