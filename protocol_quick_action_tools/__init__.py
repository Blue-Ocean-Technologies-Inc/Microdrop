# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Quick-actions contributions for the pluggable protocol tree (#433).

Architecture lives in pluggable_protocol_tree (extension point, traits
model, bar widget, controller, pane integration). This plugin
contributes the 8 legacy actions (add/delete/save/open/import/new
protocol, add group, browse reports) plus the ReportBrowserDialog.
"""
