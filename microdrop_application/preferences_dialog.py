# Enthought library imports.
from microdrop_application.menus import is_advanced_mode
from traits.api import Bool, List, observe
from traitsui.api import Item, ListEditor, View
from envisage.ui.tasks.api import PreferencesDialog as _PreferencesDialog, PreferencesTab, PreferencesCategory

advanced_mode_tab = PreferencesCategory(
    id="microdrop.advanced_mode.preferences",
    name="Advanced Mode",
)

class PreferencesDialog(_PreferencesDialog):
    """A dialog for editing preferences."""

    #### 'PreferencesDialog' interface ########################################

    # Should the Apply button be shown?
    show_apply = Bool(True)

    #### Private interface ####################################################
    _tabs_filtered =  List(PreferencesTab)

    ###########################################################################
    # Public interface
    ###########################################################################

    def select_pane(self, pane_id):
        """
        Find and activate the notebook tab that contains the given pane id.
        """
        for tab in self.get_tabs():
            for pane in tab.panes:
                if pane.id == pane_id:
                    self._selected = tab
                    return

    def get_tabs(self):
        if is_advanced_mode():
            _tabs = self._tabs
        else:
            _tabs = self._tabs_filtered

        return _tabs

    ###########################################################################
    # 'HasTraits' interface.
    ###########################################################################

    def traits_view(self):
        """Build the dynamic dialog view."""
        buttons = ["Apply", "Revert", "OK", "Cancel"]

        # Only show advanced mode tab if in advanced mode
        if is_advanced_mode():
            tab_id = "_tabs"
            # Only show the tab bar if there is more than one category.
            tabs_style = "custom" if len(self._tabs) > 1 else "readonly"
        else:
            tab_id = "_tabs_filtered"
            # Only show the tab bar if there is more than one category.
            tabs_style = "custom" if len(self._tabs_filtered) > 1 else "readonly"

        return View(
            Item(
                tab_id,
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

    ###########################################################################
    # 'Handler' interface.
    ###########################################################################

    def init(self, info):
        info.ui.history.undoable = True
        return super().init(info)

    def apply(self, info=None):
        """Handles the Apply button being clicked."""

        for tab in self.get_tabs():
            for pane in tab.panes:
                pane.apply()

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

    ###########################################################################
    # Protected interface.
    ###########################################################################

    @observe("categories")
    def _category_changed(self, event=None):
        self.categories.append(advanced_mode_tab)

    @observe("_tabs")
    def _tabs_changed(self, event=None):
        self._tabs_filtered = self._tabs[:-1]