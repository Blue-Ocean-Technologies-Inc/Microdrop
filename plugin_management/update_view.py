# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""TraitsUI layout for the launch update-check dialog: an updates section
and a new-plugins section (each hides when empty) + Update All / Later
buttons. Pure presentation — the controller handles the buttons; the model
supplies the HTML row text."""
from traitsui.api import Action, Group, HTMLEditor, Item, VGroup, View

update_all_action = Action(name="Update All", action="update_all",
                           visible_when="object.has_updates")
later_action = Action(name="Later", action="do_close")

update_view = View(
    VGroup(
        Group(
            Item("updates_html", show_label=False, style="custom",
                 editor=HTMLEditor()),
            label="Updates available",
            show_border=True,
            visible_when="has_updates",
        ),
        Group(
            Item("new_plugins_html", show_label=False, style="custom",
                 editor=HTMLEditor()),
            label="New plugins available",
            show_border=True,
            visible_when="has_new",
        ),
    ),
    buttons=[update_all_action, later_action],
    title="Plugin Updates",
    kind="livemodal",
    width=460,
    height=340,
)
