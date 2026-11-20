# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""AppUpdatesPlugin — Help > "Check for Updates…" and the background check
after startup.

The check fetches the release tags once per launch, off the GUI thread. Under
the "latest" policy it only logs that the next start moves to a new release;
under "stay" it announces each new release once.
"""

# Third-party imports.
import dramatiq

# Enthought library imports.
from envisage.api import TASK_EXTENSIONS, Plugin
from envisage.ui.tasks.api import TaskExtension
from pyface.action.schema.api import SchemaAddition
from pyface.api import GUI
from traits.api import Bool, Instance, List, Str, observe

# Microdrop package imports.
from microdrop_application.consts import PKG as microdrop_application_PKG
from microdrop_application.dialogs.pyface_wrapper import YES, confirm
from user_help_plugin.consts import HELP_ACTIONS_ADDITION_ID

# Microdrop utils imports.
from microdrop_utils.source_update_startup import (
    LAST_ANNOUNCED_PREFERENCE_PATH,
    PROJECT_ROOT,
    SKIP_GIT_UPDATE_ENV_VAR,
    skip_variable_is_set,
)
from microdrop_utils.source_version import (
    SourceVersionError,
    checkout_state,
    current_release,
    fetch_tags,
    list_release_tags,
    newest_panel_tag,
    pending_update,
)

# Local imports.
from .consts import (
    ANNOUNCE,
    LOG_DOWNLOADED,
    PKG,
    POLICY_LATEST,
    POLICY_STAY,
    PKG_name,
)
from .launch_check import launch_check_action, may_check
from .messages import newer_version_notice
from .preferences import AppUpdatesPreferences

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _tag_name(tag):
    return None if tag is None else tag.name


class AppUpdatesPlugin(Plugin):
    """The Updates dialog's menu item and the check after startup."""

    id = f"{PKG}.plugin"
    name = f"{PKG_name} Plugin"

    #: The task whose Help menu we contribute to.
    task_id_to_contribute_view = Str(f"{microdrop_application_PKG}.task")

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    #: The update settings: read on the GUI thread before the check starts,
    #: written there when a release is announced.
    preferences = Instance(AppUpdatesPreferences)

    #: True once the launch check has started (it runs exactly once).
    _launch_check_started = Bool(False)

    def _preferences_default(self):
        return AppUpdatesPreferences(preferences=self.application.preferences)

    # --- menu contribution ----------------------------------------------

    def _contributed_task_extensions_default(self):
        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                actions=[
                    SchemaAddition(
                        id="app_updates.help_actions",
                        factory=self._help_actions_group,
                        path="MenuBar/Help",
                        after=HELP_ACTIONS_ADDITION_ID,
                    )
                ],
            )
        ]

    def _help_actions_group(self):
        """Single Check for Updates action in Help."""
        from pyface.tasks.action.api import SGroup

        from .menus import CheckForUpdatesAction

        return SGroup(CheckForUpdatesAction(), id="app_updates_actions")

    # --- launch check ------------------------------------------------------

    # COLON (not dot) observe, as in plugin_management: the dot form also
    # fires when the `application` trait is assigned at construction, long
    # before the application is up.
    @observe("application:application_initialized")
    def _check_for_updates_on_launch(self, event):
        """Start the background check, once per launch. The preferences are
        read here, on the GUI thread, and handed to the worker."""
        if self._launch_check_started:
            return

        self._launch_check_started = True

        policy = POLICY_LATEST if self.preferences.auto_update else POLICY_STAY

        self._make_launch_check_actor().send(
            policy, self.preferences.last_announced_version
        )

    def _make_launch_check_actor(self):
        """Declare the one-shot launch-check actor on the shared broker.

        max_retries=0: a crash escaping the guards must not make the Retries
        middleware re-run the check (repeated fetches, repeated notices) — a
        failed check just waits for the next launch.
        """

        @dramatiq.actor(max_retries=0)
        def app_updates_launch_check(policy, last_announced):
            # Every failure is logged only: the check never interrupts the user.
            try:
                self._run_launch_check(policy, last_announced)
            except Exception as e:
                logger.warning(f"Update check failed: {e!r}", exc_info=True)

        return app_updates_launch_check

    def _run_launch_check(self, policy, last_announced):
        """Worker: gather the facts, then act on ``launch_check_action``."""
        state, reason = checkout_state(PROJECT_ROOT)
        skip_variable_set = skip_variable_is_set()

        if not may_check(state, skip_variable_set):
            # A managed checkout has no reason, so only the variable stops it.
            why = reason or f"{SKIP_GIT_UPDATE_ENV_VAR} is set"

            logger.info(f"Update check skipped: {why}")

            return

        try:
            fetch_tags(PROJECT_ROOT)
        except SourceVersionError as e:
            logger.info(f"Could not check for updates: {e}")

            return

        action, tag_name = launch_check_action(
            state=state,
            skip_variable_set=skip_variable_set,
            policy=policy,
            pending_tag=_tag_name(pending_update(PROJECT_ROOT)),
            newest_panel_tag=_tag_name(
                newest_panel_tag(list_release_tags(PROJECT_ROOT))
            ),
            current_release=current_release(PROJECT_ROOT),
            last_announced=last_announced,
        )

        if action == LOG_DOWNLOADED:
            logger.info(
                f"MicroDrop {tag_name} downloaded; it will be used the next time "
                f"MicroDrop starts."
            )

        elif action == ANNOUNCE:
            GUI.invoke_later(self._announce_release, tag_name)

    def _announce_release(self, tag_name):
        """Remember ``tag_name`` as announced, then offer the Updates dialog."""
        self.preferences.last_announced_version = tag_name

        # Saved before the notice shows, so a crash while it is open cannot
        # announce the same release at every start.
        try:
            self.preferences.preferences.flush()
        except OSError as e:
            logger.warning(f"Could not save {LAST_ANNOUNCED_PREFERENCE_PATH}: {e}")

        answer = confirm(
            None,
            newer_version_notice(tag_name),
            title="MicroDrop update",
            yes_label="View…",
            no_label="Later",
        )

        if answer == YES:
            from .menus import open_updates_dialog

            open_updates_dialog(self.application)
