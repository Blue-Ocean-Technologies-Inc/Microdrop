from pyface.tasks.api import TraitsDockPane
from traits.api import HasTraits, HTML, Str
from traitsui.api import UItem, View, HTMLEditor

from .MVC import PortableManualControlModel, PortableManualControlView, PortableManualControlControl
from .consts import PKG_name, PKG


class PortableManualControlsDockPane(TraitsDockPane):
    """A dock pane for portable dropbot controls: light intensity, chip lock, tray toggle."""

    id = Str(PKG + ".dock_pane")
    name = Str(f"{PKG_name} Dock Pane")

    model = PortableManualControlModel()
    view = PortableManualControlView
    controller = PortableManualControlControl(model)

    view.handler = controller

    def show_help(self):
        sample_text = (
            "<html><body><h1>Portable Manual Controls Help Page</h1>"
            + (self.__doc__ or "")
        )

        class HTMLEditorDemo(HasTraits):
            my_html_trait = HTML(sample_text)
            traits_view = View(
                UItem(
                    "my_html_trait",
                    editor=HTMLEditor(format_text=False),
                ),
                title="HTMLEditor",
                buttons=["OK"],
                width=800,
                height=600,
                resizable=True,
            )

        HTMLEditorDemo().configure_traits()
