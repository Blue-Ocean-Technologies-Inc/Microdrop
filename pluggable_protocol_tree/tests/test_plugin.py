"""Minimal plugin smoke tests — verify the extension point is registered."""

from pluggable_protocol_tree.plugin import PluggableProtocolTreePlugin
from pluggable_protocol_tree.consts import PROTOCOL_COLUMNS


def test_plugin_id():
    p = PluggableProtocolTreePlugin()
    assert p.id.startswith("pluggable_protocol_tree")


def test_plugin_declares_extension_point():
    p = PluggableProtocolTreePlugin()
    point_ids = [ep.id for ep in p.get_extension_points()]
    assert PROTOCOL_COLUMNS in point_ids
