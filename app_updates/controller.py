# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The updates dialog's handler: checks for new releases, confirms and runs a
switch, then closes MicroDrop.

Git and the user environment are slow, so they run behind ``run_with_wait``;
the model is refreshed afterwards on the GUI thread, never from the worker.
"""

# Enthought library imports.
from traits.api import Any, Button, Property, Str, observe
from traitsui.api import Controller

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import (
    YES,
    choose,
    confirm,
    error,
    information,
)

# Microdrop utils imports.
from microdrop_utils.pyside_helpers import markdown_text_to_html
from microdrop_utils.source_update_startup import SKIP_GIT_UPDATE_ENV_VAR
from microdrop_utils.source_version import HAS_PANEL, PLAIN, return_commands
from microdrop_utils.threaded_progress import run_with_wait
from microdrop_utils.user_environment import manual_unset_command

# Local imports.
from .messages import (
    close_message,
    forced_pull_warning,
    no_panel_warning,
    plain_confirmation,
    skip_variable_line,
    state_line,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The answers to the forced-pull warning.
SET_AND_SWITCH = "Set it and switch"
SWITCH_WITHOUT_IT = "Switch without it"


def _git_output(exc):
    """Return what git printed for a failure, or None when nothing did."""
    return getattr(exc, "output", "") or None


class UpdatesController(Controller):
    """Runs the updates dialog's buttons against an ``UpdatesModel``."""

    #: The Envisage application, exited after a successful switch; None
    #: leaves the process running (the standalone demo).
    application = Any(None)

    #: The selected release's changelog, rendered.
    changelog_html = Property(Str, observe="model.changelog_markdown")

    #: Why versions cannot be switched here; empty when they can.
    state_text = Property(Str, observe="model.state, model.state_reason")

    #: Says automatic updates are off because of the skip variable.
    skip_variable_text = Property(Str)

    #: In-body buttons; a dialog-row Action cannot sit beside the text.
    check_button = Button("Check for updates")
    remove_button = Button("Remove")

    # --- property getters ----------------------------------------------

    def _get_changelog_html(self):
        return markdown_text_to_html(self.model.changelog_markdown)

    def _get_state_text(self):
        return state_line(self.model.state, self.model.state_reason)

    def _get_skip_variable_text(self):
        return skip_variable_line(SKIP_GIT_UPDATE_ENV_VAR)

    # --- actions --------------------------------------------------------

    def check_for_updates(self, info):
        """Fetch the release tags and refresh the list; offline is a plain
        message, not an error."""
        run_with_wait(
            self.model.fetch,
            title="Checking for updates",
            message="Checking for new MicroDrop versions…",
            on_success=lambda result: self.model.refresh(),
            on_error=lambda exc: self._fetch_failed(info, exc),
        )

    def switch_version(self, info):
        """Confirm the switch to the model's target, check it out, then close
        MicroDrop."""
        if not self.model.action_enabled:
            return

        # The refresh after a switch moves ``target``, so keep its name.
        target_name = self.model.target.name
        set_variable = self._ask_how_to_switch(info, self.model.target)

        if set_variable is None:
            return

        work = self._set_skip_variable_and_switch if set_variable else self.model.switch

        run_with_wait(
            work,
            title="Switching version",
            message=f"Switching MicroDrop to {target_name}…",
            on_success=lambda result: self._switched(info, target_name),
            on_error=lambda exc: self._switch_failed(info, exc),
        )

    def remove_skip_variable(self, info):
        """Unset the skip variable for the user, so automatic updates work
        again."""
        run_with_wait(
            self.model.clear_skip_variable,
            title="Turning automatic updates back on",
            message=f"Removing {SKIP_GIT_UPDATE_ENV_VAR}…",
            on_success=lambda result: self.model.refresh(),
            on_error=lambda exc: self._remove_failed(info, exc),
        )

    def do_close(self, info):
        info.ui.dispose()

    # --- in-body buttons -----------------------------------------------

    @observe("check_button")
    def _check_button_clicked(self, event):
        self.check_for_updates(self.info)

    @observe("remove_button")
    def _remove_button_clicked(self, event):
        self.remove_skip_variable(self.info)

    # --- helpers --------------------------------------------------------

    def _ask_how_to_switch(self, info, target):
        """Ask the question ``target``'s kind calls for. Return None when the
        user cancels, else whether to set the skip variable first."""
        parent = info.ui.control
        commands = return_commands(self.model.repo_root)

        if target.kind == HAS_PANEL:
            answer = confirm(
                parent=parent,
                title="Switch version",
                informative=plain_confirmation(
                    target.name,
                    self.model.drops_unreleased_commits(),
                    self.model.frontend_only,
                ),
            )

            return False if answer == YES else None

        if target.kind == PLAIN:
            answer = confirm(
                parent=parent,
                title="Switch version",
                informative=no_panel_warning(target.name, commands),
                detail=commands,
                detail_collapsible=False,
                yes_label="Switch",
                no_label="Cancel",
            )

            return False if answer == YES else None

        unset_command = manual_unset_command(SKIP_GIT_UPDATE_ENV_VAR)

        choice = choose(
            parent=parent,
            title="Switch version",
            informative=forced_pull_warning(
                target.name, commands, SKIP_GIT_UPDATE_ENV_VAR, unset_command
            ),
            detail=f"{commands}\n\n{unset_command}",
            detail_collapsible=False,
            choices=(SET_AND_SWITCH, SWITCH_WITHOUT_IT),
            cancel=True,
        )

        if choice is None:
            return None

        return choice == SET_AND_SWITCH

    def _set_skip_variable_and_switch(self):
        """Worker: an error setting the variable stops before the switch."""
        self.model.set_skip_variable()
        self.model.switch()

    def _fetch_failed(self, info, exc):
        self.model.refresh()

        information(
            parent=info.ui.control,
            title="Check for updates",
            message="Could not check for updates. Check the internet connection.",
            detail=_git_output(exc),
            cancel=False,
        )

    def _switched(self, info, target_name):
        information(
            parent=info.ui.control,
            title="Version switched",
            message=close_message(target_name),
            cancel=False,
        )

        info.ui.dispose()

        if self.application is not None:
            self.application.exit()

    def _switch_failed(self, info, exc):
        self.model.refresh()

        error(
            parent=info.ui.control,
            title="Switch failed",
            message=str(exc),
            detail=_git_output(exc),
        )

    def _remove_failed(self, info, exc):
        self.model.refresh()

        error(
            parent=info.ui.control,
            title="Could not remove the variable",
            message=str(exc),
        )
