# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Plugin scaffold: package importable, consts defined, plugin class
declares the IQuickAction contribution list (initially empty until
the action factories land in task 12)."""

import protocol_quick_action_tools
from protocol_quick_action_tools.consts import PKG, PKG_name
from protocol_quick_action_tools.plugin import (
    ProtocolQuickActionToolsPlugin,
)


def test_package_is_importable():
    assert protocol_quick_action_tools is not None


def test_consts_match_package_layout():
    assert PKG == "protocol_quick_action_tools"
    assert PKG_name == "Protocol Quick Action Tools"


def test_plugin_id_and_name():
    p = ProtocolQuickActionToolsPlugin()
    assert p.id == "protocol_quick_action_tools.plugin"
    assert p.name == "Protocol Quick Action Tools Plugin"


def test_plugin_has_contribution_list_trait():
    p = ProtocolQuickActionToolsPlugin()
    # The factories aren't wired in yet — they land in task 12. The
    # trait must exist and default to an empty list so the scaffold
    # can be loaded by Envisage without crashing.
    assert isinstance(p.contributed_quick_actions, list)
