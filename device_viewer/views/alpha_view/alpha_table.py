from ast import Dict
from typing import Any
from traits.api import HasTraits
from traitsui.api import View, VGroup, Item, ObjectColumn, TableEditor, Label, Handler, Action, RangeEditor
from traitsui.extras.checkbox_column import CheckboxColumn
from traitsui.ui import UIInfo
from pyface.qt.QtGui import QColor, QFont
from pyface.qt.QtWidgets import QStyledItemDelegate

from device_viewer.models.main_model import MainModel
from device_viewer.views.route_selection_view.menu import RouteLayerMenu
from device_viewer.models.route import RouteLayer
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.icons.icons import ICON_VISIBILITY, ICON_VISIBILITY_OFF

def generate_alpha_view(model: MainModel):
    """Generate the alpha view for the given model."""

    return View(
        Item('alpha_map', show_label=False, editor=TableEditor(
            columns=[
                ObjectColumn(name='value', label='Value', editable=False),
                ObjectColumn(name='alpha', label='Alpha', resize_mode="stretch", editor=RangeEditor(
                    low=0.0,
                    high=1.0,
                ))
            ]
        ))
    )