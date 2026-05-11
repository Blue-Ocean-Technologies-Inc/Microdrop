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


# --- PPT-3 additions ---

def test_assemble_columns_includes_electrodes_and_routes():
    p = PluggableProtocolTreePlugin()
    ids = [c.model.col_id for c in p._assemble_columns()]
    assert "electrodes" in ids
    assert "routes" in ids


def test_assemble_columns_includes_six_hidden_config_columns():
    p = PluggableProtocolTreePlugin()
    ids = [c.model.col_id for c in p._assemble_columns()]
    for hid in ("trail_length", "trail_overlay", "soft_start",
                "soft_end", "repeat_duration", "linear_repeats"):
        assert hid in ids


def test_assemble_columns_canonical_order_after_ppt3():
    p = PluggableProtocolTreePlugin()
    ids = [c.model.col_id for c in p._assemble_columns()
           if c.model.col_id in (
               "type", "id", "name", "repetitions", "duration_s",
               "electrodes", "routes",
               "trail_length", "trail_overlay", "soft_start", "soft_end",
               "repeat_duration", "linear_repeats",
           )]
    assert ids == [
        "type", "id", "name", "repetitions", "duration_s",
        "electrodes", "routes",
        "trail_length", "trail_overlay", "soft_start", "soft_end",
        "repeat_duration", "linear_repeats",
    ]


# --- PPT-10.1.1: contribution mixing regression -----------------------

def test_extension_point_accepts_compound_columns_alongside_plain_columns():
    """Regression: when one plugin contributes ICompoundColumn and
    another contributes plain IColumn, the extension point must accept
    both. Previously the consumer typed _column_extension_point as
    List(Instance(IColumn)) which raised TraitError on compound-column
    contributions and silently dropped EVERY contribution from EVERY
    plugin — including the plain IColumn ones."""
    from traits.api import HasTraits, Instance, List

    from pluggable_protocol_tree.consts import PROTOCOL_COLUMNS
    from pluggable_protocol_tree.interfaces.i_column import IColumn
    from pluggable_protocol_tree.interfaces.i_compound_column import (
        ICompoundColumn,
    )
    from pluggable_protocol_tree.plugin import PluggableProtocolTreePlugin

    # Sanity: ICompoundColumn does NOT extend IColumn. If this changes
    # in the future the test below becomes redundant — that's fine.
    assert not issubclass(ICompoundColumn, IColumn)

    # Synthesize a fake compound column instance + a fake plain column
    # instance and inject them via the plain `contributed_columns`
    # trait (the same path Envisage uses after extension-point resolution).
    from pluggable_protocol_tree.builtins.repetitions_column import (
        make_repetitions_column,
    )
    from pluggable_protocol_tree.demos.enabled_count_compound import (
        make_enabled_count_compound,
    )

    p = PluggableProtocolTreePlugin()
    p.contributed_columns = [
        make_repetitions_column(),       # IColumn
        make_enabled_count_compound(),   # ICompoundColumn
    ]

    cols = p._assemble_columns()
    ids = [c.model.col_id for c in cols]
    # Plain IColumn contribution survives.
    assert ids.count("repetitions") >= 2  # builtin + contributed
    # Compound column expanded into its field cells.
    # enabled_count_compound exposes 'ec_enabled' + 'ec_count' fields.
    assert "ec_enabled" in ids
    assert "ec_count" in ids
