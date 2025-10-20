from traits.trait_types import Instance
from traitsui.api import View, Item, ObjectColumn, TableEditor, NumericColumn, Group
from device_viewer.views.route_selection_view.route_selection_view import VisibleColumn

alpha_table_editor = TableEditor(

    columns=[

        ObjectColumn(name='key', label="", editable=False,horizontal_alignment='left',),
        NumericColumn(name='alpha', label=""),
        VisibleColumn(name='visible', editable=False, label="", horizontal_alignment='center',),

    ],

    show_column_labels=False,
)


alpha_table_view = View(
    Group(
        Item('alpha_map', editor=alpha_table_editor, show_label=False),
        label='Alpha Settings',
        show_border=True,
    ),
)

if __name__ == '__main__':
    from traits.api import HasTraits, List, Any
    from device_viewer.default_settings import default_alphas
    from device_viewer.models.alpha import AlphaValue, AlphaModel

    alpha_model = AlphaModel()
    alpha_model.alpha_map_list = [AlphaValue(key=key, alpha=default_alphas[key]) for key in default_alphas.keys()]
    alpha_model.visibility_map = {key: True for key in default_alphas.keys()}
    alpha_model.alpha_map_list.append(AlphaValue(key="example alpha setting with long name", alpha=0.75))

    alpha_model.configure_traits(view=alpha_table_view)