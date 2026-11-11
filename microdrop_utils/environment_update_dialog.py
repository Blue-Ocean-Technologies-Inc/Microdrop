# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The user-facing "this environment is out of date" flow: explain which
package a feature is missing, offer to update the pixi-microdrop repository
(saying which local changes that discards and which plugins it re-adds), then
import the package into the running app and continue, handing over the exact
commands when that fails."""

# Enthought library imports.
from pyface.qt import QtCore

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import (
    OK,
    error,
    escape_html_multiline,
    information,
    warning,
)

# Microdrop utils imports.
from microdrop_utils.environment_update import (
    EnvironmentUpdateError,
    IExternalPluginsProvider,
    locate_update,
    make_importable,
    manual_update_commands,
    run_update_steps,
)
from microdrop_utils.threaded_progress import run_with_wait

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The warning's accept button: the update carries on in the running app.
UPDATE_LABEL = "Update"
NOT_NOW_LABEL = "Not now"

#: The progress dialog the update runs behind.
UPDATE_TITLE = "Updating MicroDrop"
UPDATE_MESSAGE = "Updating the pixi-microdrop repository and environment…"

#: The update by hand when it cannot be planned (checkout not located,
#: installed plugins unknown).
GENERIC_MANUAL_UPDATE = (
    "In your pixi-microdrop folder: git reset --hard, then git pull\n"
    "Then in its microdrop-py folder: pixi install\n"
    "Then reinstall your plugins from Tools > Manage Plugins"
)


def missing_package_message(feature, package):
    """The standard explanation that ``feature`` needs ``package``."""
    return (
        f"<strong>{feature}</strong> needs the <strong>{package}</strong> "
        "package, which this environment does not have. Update the "
        "<strong>pixi-microdrop</strong> repository to install it."
    )


def reset_notice(plan):
    """What the update ``plan`` does to the launcher checkout: the branch it
    switches to, the local changes it discards, and the external plugins it
    re-adds."""
    switch = (
        "The <strong>pixi-microdrop</strong> repository will be switched to "
        f"its <strong>{plan.branch}</strong> branch and updated."
    )

    if not plan.plugins:
        return (
            f"{switch} Local changes to the launcher's pyproject.toml, "
            "pixi.lock and other tracked files will be discarded; no external "
            "plugins are installed, so none need re-adding."
        )

    names = "<br>".join(f"- <strong>{plugin.name}</strong>" for plugin in plan.plugins)

    return (
        f"{switch} Local changes to the launcher's pyproject.toml, pixi.lock "
        "and other tracked files will be discarded and these plugins re-added "
        f"afterwards:<br><br>{names}"
    )


def offer_environment_update(feature, package, application=None):
    """Tell the user ``feature`` needs ``package`` and offer to update the
    pixi-microdrop repository (reset, ``git pull``, re-add the installed
    plugins, ``pixi install``); ``application``'s
    ``IExternalPluginsProvider`` service tells the plugins. The update runs
    behind a progress dialog.

    Waits for the update, then imports ``package`` into the running app and
    returns True when the caller can retry ``feature`` right away — False on
    "Not now" or when the update or import failed (already reported to the
    user)."""
    message = missing_package_message(feature, package)
    logger.warning(message)

    # Planned before asking, so the question can name what the update
    # discards and re-adds; a plan that fails is reported once the user
    # chooses to update.
    plan = failure = None

    try:
        plan = locate_update(plugins_provider=_external_plugins_provider(application))
    except EnvironmentUpdateError as e:
        failure = e

    if failure is None:
        message = f"{message}<br><br>{reset_notice(plan)}"

    choice = warning(
        None,
        message,
        title="Update required",
        ok_label=UPDATE_LABEL,
        cancel_label=NOT_NOW_LABEL,
    )

    if choice != OK:
        return False

    if failure is not None:
        _report_update_failure(failure, GENERIC_MANUAL_UPDATE)

        return False

    commands = manual_update_commands(plan.steps)

    return _update_in_place(feature, package, plan, commands)


def report_package_still_missing(package):
    """Show that ``package`` is still missing after an update that reported
    success, with the commands to update by hand."""
    _report_update_failure(
        EnvironmentUpdateError(f"{package} is still not available after it."),
        GENERIC_MANUAL_UPDATE,
    )


def _external_plugins_provider(application):
    """The ``application``'s IExternalPluginsProvider service, or None."""
    if application is None:
        return None

    return application.get_service(IExternalPluginsProvider)


def _update_in_place(feature, package, plan, commands):
    """Run the ``plan`` behind the progress dialog and wait for it, then
    import ``package`` into the running app. Returns whether ``feature`` can
    carry on; a failure is reported to the user."""
    finished = []
    waiting = QtCore.QEventLoop()

    def finish(succeeded):
        finished.append(succeeded)
        waiting.quit()

    def fail(exception):
        _report_update_failure(exception, commands)
        finish(False)

    run_with_wait(
        lambda: run_update_steps(plan.steps),
        title=UPDATE_TITLE,
        message=UPDATE_MESSAGE,
        on_success=lambda _result: finish(True),
        on_error=fail,
    )

    # The update finishes on the event loop after run_with_wait returns; the
    # progress dialog is application-modal meanwhile, like any dialog.
    if not finished:
        waiting.exec()

    if not finished[0]:
        return False

    try:
        make_importable(package)
    except EnvironmentUpdateError as e:
        logger.error(f"Environment update finished, but {e}")
        information(
            None,
            f"The environment is up to date, but <strong>{package}</strong> "
            "could not be loaded into the running MicroDrop. Restart MicroDrop "
            "to use it.",
            title="Update complete",
            cancel=False,
        )

        return False

    information(
        None,
        f"Update complete. <strong>{feature}</strong> can continue.",
        title="Update complete",
        cancel=False,
    )

    return True


def _report_update_failure(exception, commands):
    """Show why the update failed and the ``commands`` to run by hand."""
    logger.error(f"Environment update failed: {exception}")

    error(
        None,
        f"The update failed: {escape_html_multiline(str(exception))}<br><br>"
        "Close MicroDrop, then run these commands by hand:<br><br>"
        f"{escape_html_multiline(commands)}",
        title="Update failed",
        detail=getattr(exception, "output", "") or None,
    )


if __name__ == "__main__":
    # Manual demo of the dialogs, never touching the real launcher or
    # environment: planning, the update steps and the import are stand-ins.
    #   python -m microdrop_utils.environment_update_dialog
    #       [--fail | --no-plugins | --unplanned]

    # Standard library imports.
    import argparse
    import sys
    import time
    from pathlib import Path

    # Enthought library imports.
    from pyface.qt import QtWidgets

    # Microdrop style imports.
    from microdrop_style.helpers import style_app

    # Microdrop utils imports.
    from microdrop_utils.environment_update import (
        ExternalPlugin,
        UpdatePlan,
        update_steps,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    outcome = parser.add_mutually_exclusive_group()
    outcome.add_argument("--fail", action="store_true", help="the update fails")
    outcome.add_argument(
        "--no-plugins", action="store_true", help="no external plugins installed"
    )
    outcome.add_argument(
        "--unplanned", action="store_true", help="the update cannot be planned"
    )
    args = parser.parse_args()

    class DemoPluginsProvider:
        """Two installed plugins (none with ``--no-plugins``)."""

        def installed_external_plugins(self, workspace):
            if args.no_plugins:
                return []

            return [
                ExternalPlugin(name="heater-microdrop-plugin"),
                ExternalPlugin(name="magnet-microdrop-plugin", version="1.2.0"),
            ]

        def reinstall_arguments(self, plugin):
            spec = f"{plugin.name}=={plugin.version}" if plugin.version else plugin.name

            return [["add", spec]]

    class DemoApplication:
        """Offers the provider (none with ``--unplanned``)."""

        def get_service(self, protocol):
            if args.unplanned or protocol is not IExternalPluginsProvider:
                return None

            return DemoPluginsProvider()

    def locate_update(plugins_provider=None):
        if plugins_provider is None:
            raise EnvironmentUpdateError(
                "Plugin management is not running, so the installed plugins "
                "cannot be told and would be lost by the update."
            )

        workspace = Path("pixi-microdrop/microdrop-py")
        plugins = plugins_provider.installed_external_plugins(workspace)
        reinstall = [
            arguments
            for plugin in plugins
            for arguments in plugins_provider.reinstall_arguments(plugin)
        ]

        branch = "master"

        return UpdatePlan(
            steps=update_steps(workspace, workspace.parent, None, reinstall, branch),
            plugins=plugins,
            branch=branch,
        )

    def run_update_steps(steps):
        print(f"Would run:\n{manual_update_commands(steps)}")
        time.sleep(1.5)

        if args.fail:
            raise EnvironmentUpdateError(
                "`pixi install` exited with code 1",
                "Updating lock file\n"
                "Error: failed to solve the environment\n"
                "  heater-microdrop-plugin cannot be installed",
            )

    def make_importable(package):
        print(f"make_importable({package!r})")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    style_app(app)

    TRASH_FEATURE = "Sending experimental folders to the Trash"
    TRASH_PACKAGE = "send2trash"

    can_continue = offer_environment_update(
        TRASH_FEATURE, TRASH_PACKAGE, application=DemoApplication()
    )
    print(f"offer_environment_update returned {can_continue}")
