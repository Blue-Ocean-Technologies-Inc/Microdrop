# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from envisage.api import Plugin
from traits.api import List


class PlotViewPlugin(Plugin):
    id = 'app.plot.view.plugin'
    views = List(contributes_to='app.ui.views')

    def start(self):
        super(PlotViewPlugin, self).start()
        self.views.append('Plot View')
        print("Plot View Plugin started and contributed a view.")
