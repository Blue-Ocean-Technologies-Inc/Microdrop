# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Interface-module smoke tests.

These are lightweight: interfaces don't have behaviour, so we check only
that the interface classes can be imported and subclass the Traits
`Interface` base correctly.
"""

from traits.api import Interface

from pluggable_protocol_tree.interfaces.i_row import IRow, IGroupRow


def test_i_row_is_interface():
    assert issubclass(IRow, Interface)


def test_i_group_row_extends_i_row():
    assert issubclass(IGroupRow, IRow)


from pluggable_protocol_tree.interfaces.i_column import (
    IColumnModel, IColumnView, IColumnHandler, IColumn,
)


def test_column_interfaces_are_interfaces():
    for iface in (IColumnModel, IColumnView, IColumnHandler, IColumn):
        assert issubclass(iface, Interface)
