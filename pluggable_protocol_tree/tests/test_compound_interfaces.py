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
