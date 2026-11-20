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
    warning,
)

# Microdrop utils imports.
from microdrop_utils.source_update_startup import SKIP_GIT_UPDATE_ENV_VAR
from microdrop_utils.source_version import (
    FORCED_PULL,
    HAS_PANEL,
    PLAIN,
    return_commands,
)
from microdrop_utils.threaded_progress import run_with_wait
from microdrop_utils.user_environment import manual_unset_command

# Local imports.
from .consts import SET_AND_SWITCH, SWITCH_WITHOUT_IT
from .messages import (
    close_message,
    forced_pull_warning,
    no_panel_warning,
    plain_confirmation,
    skip_variable_failed_message,
    skip_variable_line,
    state_line,
    still_running_warning,
    switch_failed_message,
)
from .view import themed_changelog_html

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class SkipVariableNotSet(Exception):
    """Saving the skip variable failed, so the switch was not attempted."""


def _git_output(exc):
    """Return what git printed for a failure, or None when nothing did."""
    return getattr(exc, "output", "") or None


def _line_count(text):
    """Return the lines a details block needs to show all of ``text``
    without scrolling: one more than it holds, as the block's padding clips
    the last line otherwise."""
    return text.count("\n") + 2


class UpdatesController(Controller):
    """Runs the updates dialog's buttons against an ``UpdatesModel``."""

    #: The Envisage application, exited after a successful switch; None
    #: leaves the process running (the standalone demo).
    application = Any(None)

    #: The selected release's changelog, rendered in the dialog's theme.
    changelog_html = Property(Str, observe="model.changelog_markdown")

    #: Why versions cannot be switched here; empty when they can.
    state_text = Property(Str, observe="model.state, model.state_reason")

    #: Says automatic updates are off because of the skip variable.
    skip_variable_text = Str(skip_variable_line(SKIP_GIT_UPDATE_ENV_VAR))

    #: Fetches the release tags; an in-body button beside the version line.
    check_button = Button("Check for updates")

    #: Unsets the skip variable; an in-body button beside its line.
    remove_button = Button("Remove")

    # --- property getters ----------------------------------------------

    def _get_changelog_html(self):
        return themed_changelog_html(self.model.changelog_markdown)

    def _get_state_text(self):
        return state_line(self.model.state, self.model.state_reason)

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
            on_error=lambda exc: self._switch_failed(
                info, exc, target_name, set_variable
            ),
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
                informative=no_panel_warning(target.name),
                detail=commands,
                detail_collapsible=False,
                detail_visible_lines=_line_count(commands),
                yes_label="Switch",
                no_label="Cancel",
            )

            return False if answer == YES else None

        if target.kind == FORCED_PULL:
            unset_command = manual_unset_command(SKIP_GIT_UPDATE_ENV_VAR)
            detail = f"{commands}\n\n{unset_command}"

            choice = choose(
                parent=parent,
                title="Switch version",
                informative=forced_pull_warning(target.name, SKIP_GIT_UPDATE_ENV_VAR),
                detail=detail,
                detail_collapsible=False,
                detail_visible_lines=_line_count(detail),
                choices=(SET_AND_SWITCH, SWITCH_WITHOUT_IT),
                cancel=True,
            )

            if choice is None:
                return None

            return choice == SET_AND_SWITCH

        logger.error(f"Not switching to {target.name}: unknown kind {target.kind!r}")
        error(
            parent=parent,
            title="Switch version",
            message=f"MicroDrop cannot tell how to switch to {target.name}.",
        )

        return None

    def _set_skip_variable_and_switch(self):
        """Worker: a failure saving the variable stops before the switch."""
        try:
            self.model.set_skip_variable()
        except OSError as e:
            raise SkipVariableNotSet(str(e)) from e

        self.model.switch()

    def _fetch_failed(self, info, exc):
        logger.error(f"Could not check for updates: {exc}")
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

        # A window may veto the exit (an unsaved protocol, a failed layout
        # save), leaving the old version running on the new source.
        if self.application is not None and self.application.exit() is not True:
            logger.error(f"MicroDrop did not close after switching to {target_name}")
            warning(
                parent=None,
                title="Restart MicroDrop",
                message=still_running_warning(target_name),
                cancel=False,
            )

    def _switch_failed(self, info, exc, target_name, set_variable):
        if isinstance(exc, SkipVariableNotSet):
            message = skip_variable_failed_message(SKIP_GIT_UPDATE_ENV_VAR)
        else:
            variable = SKIP_GIT_UPDATE_ENV_VAR if set_variable else None
            message = switch_failed_message(target_name, variable)

        logger.error(f"{message} {exc}")
        self.model.refresh()

        error(
            parent=info.ui.control,
            title="Switch failed",
            message=f"{message}\n\n{exc}",
            detail=_git_output(exc),
        )

    def _remove_failed(self, info, exc):
        logger.error(f"Could not remove {SKIP_GIT_UPDATE_ENV_VAR}: {exc}")
        self.model.refresh()

        error(
            parent=info.ui.control,
            title="Could not remove the variable",
            message=f"Could not remove {SKIP_GIT_UPDATE_ENV_VAR}.\n\n{exc}",
        )
