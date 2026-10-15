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
(saying which local changes that discards and which plugins it re-adds) and
relaunch, and hand over the exact commands when that fails."""

# Standard library imports.
import html

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
    manual_update_commands,
    relaunch,
    run_update_steps,
)
from microdrop_utils.threaded_progress import run_with_wait

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

UPDATE_AND_RELAUNCH_LABEL = "Update and relaunch"
NOT_NOW_LABEL = "Not now"

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
        f"{feature} needs the {package} package, which this environment does "
        "not have. Update the pixi-microdrop repository to install it."
    )


def reset_notice(plugins):
    """What the update discards, and the external ``plugins`` it re-adds."""
    if not plugins:
        return (
            "Local changes to the launcher's pyproject.toml, pixi.lock and "
            "other tracked files will be discarded; no external plugins are "
            "installed, so none need re-adding."
        )

    names = ", ".join(plugin.name for plugin in plugins)

    return (
        "Local changes to the launcher's pyproject.toml, pixi.lock and other "
        "tracked files will be discarded and these plugins re-added "
        f"afterwards: {names}."
    )


def offer_environment_update(feature, package, application=None):
    """Tell the user ``feature`` needs ``package`` and offer to update the
    pixi-microdrop repository (reset, ``git pull``, re-add the installed
    plugins, ``pixi install``) and relaunch ``application``, whose
    ``IExternalPluginsProvider`` service tells the plugins. Returns True
    when the user chose to update (the update then runs behind a progress
    dialog), False on "Not now"."""
    message = missing_package_message(feature, package)
    logger.warning(message)

    # Planned before asking, so the question can name what the update
    # discards and re-adds; a plan that fails is reported once the user
    # chooses to update.
    steps = plugins = failure = None

    try:
        steps, plugins = locate_update(
            plugins_provider=_external_plugins_provider(application)
        )
    except EnvironmentUpdateError as e:
        failure = e

    if failure is None:
        message = f"{message}<br><br>{html.escape(reset_notice(plugins))}"

    choice = warning(
        None,
        message,
        title="Update required",
        ok_label=UPDATE_AND_RELAUNCH_LABEL,
        cancel_label=NOT_NOW_LABEL,
    )

    if choice != OK:
        return False

    if failure is not None:
        _report_update_failure(failure, GENERIC_MANUAL_UPDATE)

        return True

    commands = manual_update_commands(steps)

    run_with_wait(
        lambda: run_update_steps(steps),
        title="Updating MicroDrop",
        message="Updating the pixi-microdrop repository and environment…",
        on_success=lambda _result: _relaunch_after_update(application),
        on_error=lambda e: _report_update_failure(e, commands),
    )

    return True


def _external_plugins_provider(application):
    """The ``application``'s IExternalPluginsProvider service, or None."""
    if application is None:
        return None

    return application.get_service(IExternalPluginsProvider)


def _relaunch_after_update(application):
    """Relaunch; reaching the end means the exit was vetoed or the new
    process could not start, so the user restarts by hand."""
    try:
        relaunch(application)
    except OSError as e:
        logger.error(f"Relaunch after the environment update failed: {e}")

    information(
        None,
        "The environment is up to date. Restart MicroDrop to use it.",
        title="Update complete",
        cancel=False,
    )


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
