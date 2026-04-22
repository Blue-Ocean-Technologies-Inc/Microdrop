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


# --- PPT-2 additions ---

def test_assemble_columns_includes_repetitions():
    p = PluggableProtocolTreePlugin()
    cols = p._assemble_columns()
    ids = [c.model.col_id for c in cols]
    assert "repetitions" in ids


def test_assemble_columns_canonical_order():
    """Built-ins land in: type, id, name, repetitions, duration_s order."""
    p = PluggableProtocolTreePlugin()
    cols = p._assemble_columns()
    builtin_ids = [c.model.col_id for c in cols
                   if c.model.col_id in ("type", "id", "name",
                                         "repetitions", "duration_s")]
    assert builtin_ids == ["type", "id", "name", "repetitions", "duration_s"]
