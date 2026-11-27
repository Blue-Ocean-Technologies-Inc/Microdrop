# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from envisage.api import PREFERENCES_CATEGORIES, PREFERENCES_PANES
from envisage.ui.tasks.api import PreferencesCategory, PreferencesTab
from envisage.ui.tasks.api import PreferencesDialog as _PreferencesDialog
from traits.api import Bool, List, observe
from traitsui.api import Item, ListEditor, View

# Local imports.
from .menus import is_advanced_mode

advanced_mode_tab = PreferencesCategory(
    id="microdrop.advanced_mode.preferences",
    name="Advanced Mode",
)


class PreferencesDialog(_PreferencesDialog):
    """A dialog for editing preferences.

    The application caches this dialog as a service, so it reads the
    contributed panes and categories each time it opens: a plugin loaded or
    removed since the last open adds or drops its tabs.
    """

    #### 'PreferencesDialog' interface ########################################

    # Should the Apply button be shown?
    show_apply = Bool(True)

    #### Private interface ####################################################
    _tabs_filtered = List(PreferencesTab)

    #: The PREFERENCES_CATEGORIES contributions the tabs were built from.
    _contributed_categories = List()

    #: The PREFERENCES_PANES factories the tabs were built from.
    _contributed_pane_factories = List()

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

    def open_on_pane(self, pane_id, parent=None):
        """Open the dialog, modal over ``parent``, on the tab holding pane
        ``pane_id``; return whether it closed on OK."""
        # The tabs exist only once the loaded plugins' panes are followed.
        self._follow_contributions()
        self.select_pane(pane_id)

        ui = self.edit_traits(parent=parent, kind="livemodal")

        return ui.result

    def get_tabs(self):
        if is_advanced_mode():
            _tabs = self._tabs
        else:
            _tabs = self._tabs_filtered

        return _tabs

    ###########################################################################
    # 'HasTraits' interface.
    ###########################################################################

    def edit_traits(self, *args, **kwargs):
        """Open the dialog on the panes of the plugins loaded now."""
        self._follow_contributions()

        return super().edit_traits(*args, **kwargs)

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

        # Only handle calls when the dialog is visible. Envisage / traitsui
        # backend has set up livemodal dialogs to call revert on closing the
        # dialog window which did not even do anything since the super class
        # revert returned nothing. Since we are changing the revert to do
        # changes, we need to make sure to avoid the revert call on dialog close.

        def _choose_preference_trait_for_revert(trait_name):
            # Persisted preference traits revert to their defaults, except those
            # tagged `no_revert=True` in their declaration, which keep their
            # current value when the user presses Revert.
            return (
                pane._model._is_preference_trait(trait_name)
                and not pane._model.trait(trait_name).no_revert
            )

        if info.ui.control.isVisible():
            # find all the panes in the selected tab, and reset their
            # preference traits.
            for pane in self._selected.panes:
                trait_names = list(
                    filter(
                        _choose_preference_trait_for_revert,
                        pane._model.trait_names(),
                    )
                )

                pane._model.reset_traits(trait_names)

                pane.apply()

        return

    ###########################################################################
    # Protected interface.
    ###########################################################################

    def _follow_contributions(self):
        """Rebuild the tabs if the loaded plugins' panes or categories changed
        since they were last built. Unchanged contributions keep their panes,
        so reopening the dialog behaves as before."""
        categories = self.application.get_extensions(PREFERENCES_CATEGORIES)
        pane_factories = self.application.get_extensions(PREFERENCES_PANES)

        if (
            categories == self._contributed_categories
            and pane_factories == self._contributed_pane_factories
        ):
            return

        selected_name = self._selected.name if self._selected is not None else None

        self._contributed_categories = categories
        self._contributed_pane_factories = pane_factories
        self.trait_set(
            categories=categories,
            panes=[factory(dialog=self) for factory in pane_factories],
        )

        # Reopen on the tab the user last had open, if it is still there.
        self._selected = next(
            (tab for tab in self._tabs if tab.name == selected_name), None
        )

    @observe("categories")
    def _category_changed(self, event=None):
        self.categories.append(advanced_mode_tab)

    @observe("_tabs")
    def _tabs_changed(self, event=None):
        self._tabs_filtered = self._tabs[:-1]
