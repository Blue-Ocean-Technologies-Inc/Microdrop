# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Smoke tests for the ICompoundColumn family — confirms the module
imports and the four interfaces + FieldSpec can be referenced."""


def test_interfaces_importable():
    from pluggable_protocol_tree.interfaces.i_compound_column import (
        FieldSpec, ICompoundColumn, ICompoundColumnHandler,
        ICompoundColumnModel, ICompoundColumnView,
    )
    assert FieldSpec._fields == ("field_id", "col_name", "default_value")


def test_field_spec_construction():
    from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
    spec = FieldSpec(field_id="foo", col_name="Foo", default_value=42)
    assert spec.field_id == "foo"
    assert spec.col_name == "Foo"
    assert spec.default_value == 42
