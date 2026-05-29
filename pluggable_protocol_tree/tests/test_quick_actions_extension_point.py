"""The tree plugin exposes PROTOCOL_QUICK_ACTIONS as an Envisage
extension point. Like PROTOCOL_COLUMNS, plugin.start() copies
contributions into a plain list, and the dock-pane factory passes
that list into ProtocolTreePane(quick_actions=...).

The tree plugin itself contributes zero builtins."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction
from pluggable_protocol_tree.plugin import PluggableProtocolTreePlugin


def test_plugin_ships_zero_builtin_quick_actions():
    plugin = PluggableProtocolTreePlugin()
    # No contribution list set yet -> empty default.
    assert plugin.contributed_quick_actions == []


def test_assemble_quick_actions_sorts_by_priority_then_action_id():
    plugin = PluggableProtocolTreePlugin()
    plugin.contributed_quick_actions = [
        BaseQuickAction(action_id="z", priority=10),
        BaseQuickAction(action_id="a", priority=20),
        BaseQuickAction(action_id="c", priority=10),
    ]
    assembled = plugin._assemble_quick_actions()
    assert [a.action_id for a in assembled] == ["c", "z", "a"]
