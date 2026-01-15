# Enthought library imports.
from traits.api import Bool
from traitsui.api import Item, ListEditor, View
from envisage.ui.tasks.api import PreferencesDialog as _PreferencesDialog

class PreferencesDialog(_PreferencesDialog):
    # Should the Apply button be shown?
    show_apply = Bool(True)

    def _apply_clicked(self, info=None):
        """
        Apply preferences on a tab by tab basis
        """

        for pane in self._selected.panes:
            pane.apply()

    def revert(self, info=None):
        """
        Revert preferences on a tab by tab basis
        """
        # Only handle calls when the dialog is visible. Envisage / traitsui backend has set up livemodal dialogs to call
        # revert on closing the dialog window which did not even do anything since the super class revert returned nothing.
        # Since we are changing the revert to do changes, we need to make sure to avoid the revert call on dialog close.

        if info.ui.control.isVisible():

            # find all the panes in the selected tab, and reset their preference traits.
            for pane in self._selected.panes:

                trait_names = list(
                    filter(
                        pane._model._is_preference_trait,
                        pane._model.trait_names(),
                    )
                )

                pane._model.reset_traits(trait_names)

                pane.apply()

        return

    def traits_view(self):
        """Build the dynamic dialog view."""
        buttons = ["Apply", "Revert", "OK", "Cancel"]

        # Only show the tab bar if there is more than one category.
        tabs_style = "custom" if len(self._tabs) > 1 else "readonly"

        return View(
            Item(
                "_tabs",
                editor=ListEditor(
                    page_name=".name",
                    style="custom",
                    use_notebook=True,
                    selected="_selected",
                ),
                show_label=False,
                style=tabs_style,
            ),
            buttons=buttons,
            kind="livemodal",
            resizable=True,
            title="Preferences",
        )

    def init(self, info):
        info.ui.history.undoable = True
        return super().init(info)