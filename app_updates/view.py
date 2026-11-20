# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Help > "Check for Updates…" dialog: the running version, the update
policy, the release list beside the selected release's changelog, and the
switch action. Pure layout — ``UpdatesController`` runs the buttons."""

# Enthought library imports.
from traitsui.api import (
    Action,
    EnumEditor,
    HGroup,
    HSplit,
    HTMLEditor,
    Item,
    Label,
    TableEditor,
    UItem,
    VGroup,
    View,
    spring,
)

# Microdrop style imports.
from microdrop_style.colors import GREY
from microdrop_style.helpers import is_dark_mode

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import ObjectColumn

# Local imports.
from .consts import POLICY_LATEST, POLICY_STAY


class MutedColumn(ObjectColumn):
    """A column of secondary notes, drawn in grey."""

    def get_text_color(self, object):
        return GREY["lighter"] if is_dark_mode() else GREY["dark"]


# A TraitsUI Action caption is fixed once the button is built, so the switch
# button keeps one caption and ``action_label`` is shown on the line above it.
switch_action = Action(
    name="Switch and close",
    action="switch_version",
    enabled_when="action_enabled",
)
close_action = Action(name="Close", action="do_close")

versions_table = TableEditor(
    columns=[
        ObjectColumn(name="name", label="Version", editable=False),
        ObjectColumn(name="date", label="Date", editable=False),
        MutedColumn(name="marker", label="", editable=False),
    ],
    editable=False,
    sortable=False,
    selected="selected",
    auto_size=True,
)

version_line = HGroup(
    Item("current_description", style="readonly", label="Running"),
    spring,
    UItem("handler.check_button", enabled_when="is_managed"),
)

state_lines = VGroup(
    UItem("handler.state_text", style="readonly", visible_when="not is_managed"),
    HGroup(
        UItem("handler.skip_variable_text", style="readonly"),
        UItem("handler.remove_button"),
        visible_when="skip_variable_set",
    ),
)

policy_choice = UItem(
    "policy",
    style="custom",
    editor=EnumEditor(
        values={
            POLICY_LATEST: "1:Always use the latest version",
            POLICY_STAY: "2:Stay on a specific version",
        },
        cols=1,
    ),
    enabled_when="is_managed",
)

# The table stays enabled in every state: browsing the releases and their
# changelogs is what a development checkout still offers.
versions_and_changelog = HSplit(
    UItem("versions", editor=versions_table),
    UItem("handler.changelog_html", editor=HTMLEditor(open_externally=True)),
)

footer = VGroup(
    Label(
        "The environment and pixi-microdrop are updated from the "
        "Setup & Launcher, not here."
    ),
    HGroup(spring, UItem("action_label", style="readonly")),
)

updates_view = View(
    VGroup(version_line, state_lines, policy_choice, versions_and_changelog, footer),
    title="MicroDrop Updates",
    width=760,
    height=480,
    resizable=True,
    buttons=[switch_action, close_action],
    kind="livemodal",
)
