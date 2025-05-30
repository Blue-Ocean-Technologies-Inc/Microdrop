# enthought imports
from pyface.tasks.api import TraitsDockPane
from traits.api import HasTraits, HTML
from traitsui.api import UItem, View, HTMLEditor

# local imports
from .MVC import ManualControlModel, ManualControlView, ManualControlControl
from .consts import PKG_name, PKG


class ManualControlsDockPane(TraitsDockPane):
    """
    A dock pane to set the voltage and frequency of the dropbot device.
    """
    #### 'ITaskPane' interface ################################################

    id = PKG + ".dock_pane"
    name = f"{PKG_name} Dock Pane"

    #### 'ManualControlsPane' interface ##########################################

    model = ManualControlModel()
    view = ManualControlView
    controller = ManualControlControl(model)

    view.handler = controller

    def show_help(self):
        # Sample text to display as HTML: header, plus module docstring, plus
        # some lists. The docstring and lists will be auto-formatted
        # (format_text=True).
        sample_text = (
                """
            <html><body><h1>Manual Controls Help Page</h1>
    
            """
                + self.__doc__
        )

        class HTMLEditorDemo(HasTraits):
            """Defines the main HTMLEditor demo class."""

            # Define a HTML trait to view
            my_html_trait = HTML(sample_text)

            # Demo view
            traits_view = View(
                UItem(
                    'my_html_trait',
                    # we specify the editor explicitly in order to set format_text:
                    editor=HTMLEditor(format_text=False),
                ),
                title='HTMLEditor',
                buttons=['OK'],
                width=800,
                height=600,
                resizable=True,
            )

        # Create the demo:
        demo = HTMLEditorDemo()
        demo.configure_traits()
