from fontTools.t1Lib import eexec_IV
from traits.api import Instance, observe
from traitsui.api import View, Item, ObjectColumn, Group, Action, Handler, Menu, TableEditor

from device_viewer.default_settings import default_alphas, default_visibility
from microdrop_utils.traitsui_qt_helpers import VisibleColumn, RangeColumn

class ExTableEditor(TableEditor):
    def __init__(self, **traits):
        super().__init__(**traits)

    @observe('selected_row')
    def check_selected(self, event):
        print(event)

alpha_table_editor = TableEditor(

    columns=[
        VisibleColumn(name='visible', editable=False, label="", horizontal_alignment='center',),
        ObjectColumn(name='key', label="", editable=False,horizontal_alignment='left',),
        RangeColumn(name='alpha', label="", width=65)
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
    from traits.api import HasTraits, List, Str, Float, Bool, Range


    class AlphaValue(HasTraits):
        """A class to represent an alpha value with a key."""
        key = Str()  # The key for the alpha value
        alpha = Range(0, 100, mode="spinner")  # The alpha value associated with the key
        visible = Bool(True)  # Whether the alpha value is visible in the UI

    class AlphaModel(HasTraits):
        alpha_map = List(Instance(AlphaValue))

        @observe("alpha_map.items.[alpha, visible]")
        def update_alpha_map(self, event):
            print(event)

    alpha_model = AlphaModel()
    alpha_model.alpha_map = [AlphaValue(key=key, alpha=int(default_alphas[key])) for key in default_alphas.keys()]
    # alpha_model.alpha_map.append(AlphaValue(key="example alpha setting with long name", alpha=75))

    alpha_model.configure_traits(view=alpha_table_view)