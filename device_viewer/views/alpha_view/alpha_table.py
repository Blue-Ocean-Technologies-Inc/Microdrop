from traits.api import Instance, observe
from traitsui.api import View, Item, ObjectColumn, TableEditor, NumericColumn, Group, Action, Handler, Menu

from device_viewer.views.route_selection_view.route_selection_view import VisibleColumn
from device_viewer.default_settings import default_alphas, default_visibility

alpha_table_editor = TableEditor(

    columns=[

        ObjectColumn(name='key', label="", editable=False,horizontal_alignment='left',),
        NumericColumn(name='alpha', label=""),
        VisibleColumn(name='visible', editable=False, label="", horizontal_alignment='center',),

    ],

# Define the context menu:
    menu = Menu(
        Action(name='Reset Defaults', action='reset_defaults'),
    ),

    show_column_labels=False,
)

class AlphaHandler(Handler):
    def reset_defaults(self, info, object):
        model = info.object
        for alpha_value in model.alpha_map:
            alpha_value.alpha = default_alphas[alpha_value.key]
            alpha_value.visible = default_visibility[alpha_value.key]

alpha_table_view = View(
    Group(
        Item('alpha_map', editor=alpha_table_editor, show_label=False),
        label='Alpha Settings',
        show_border=True,
    ),
    handler=AlphaHandler()

)

if __name__ == '__main__':
    from traits.api import HasTraits, List
    from device_viewer.models.alpha import AlphaValue

    class AlphaModel(HasTraits):
        alpha_map = List(Instance(AlphaValue))

        @observe("alpha_map.items.[alpha, visible]")
        def update_alpha_map(self, event):
            print(f"{event.object.key}, {event.name}, {event.new}")

    alpha_model = AlphaModel()
    alpha_model.alpha_map = [AlphaValue(key=key, alpha=default_alphas[key]) for key in default_alphas.keys()]
    alpha_model.alpha_map.append(AlphaValue(key="example alpha setting with long name", alpha=0.75))

    alpha_model.configure_traits(view=alpha_table_view)