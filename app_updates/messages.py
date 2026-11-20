# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The texts of the updates dialogs.

The dialog bodies are HTML: version names are ``vX.Y.Z`` and go in as they
are, and every other value is escaped, so it is never taken as markup. The
commands the warnings refer to are not in the bodies; the dialogs show them
once, as copyable details. Functions marked PLAIN return plain text.
"""

# Standard library imports.
import html

# Microdrop utils imports.
from microdrop_utils.source_version import DEFAULT_BRANCH, DEVELOPMENT, NO_GIT


def _paragraphs(*paragraphs):
    return "<br><br>".join(paragraphs)


def _unreleased_paragraphs(target, drops_unreleased):
    if not drops_unreleased:
        return []

    return [
        f"You are running unreleased commits made after the last release; "
        f"{target} does not include them."
    ]


def _no_panel_paragraphs(target, drops_unreleased):
    return [
        f"{target} has no Updates panel, so MicroDrop cannot bring you back "
        f"from inside the app.",
        *_unreleased_paragraphs(target, drops_unreleased),
        "To return to the latest version, use the Setup &amp; Launcher, or "
        "run the commands below.",
    ]


def plain_confirmation(target, drops_unreleased, frontend_only):
    """Return the confirmation for switching to a release with the Updates
    panel."""
    paragraphs = [
        f"Switch MicroDrop to {target}? MicroDrop closes once it is done.",
        *_unreleased_paragraphs(target, drops_unreleased),
    ]

    if frontend_only:
        paragraphs.append(
            f"The backend runs separately: restart the backend too, so it also "
            f"runs {target}."
        )

    return _paragraphs(*paragraphs)


def no_panel_warning(target, drops_unreleased):
    """Return the warning for switching to a release without the Updates
    panel; the dialog shows the return commands below it."""
    return _paragraphs(
        *_no_panel_paragraphs(target, drops_unreleased),
        f"Switch to {target} anyway?",
    )


def forced_pull_warning(target, drops_unreleased, variable):
    """Return the warning for switching to a release that pulls ``main`` at
    every start unless ``variable`` is set; the dialog shows the return
    commands and the command removing the variable below it."""
    return _paragraphs(
        *_no_panel_paragraphs(target, drops_unreleased),
        f"{target} also updates itself: at its next start it checks out "
        f"{DEFAULT_BRANCH} and pulls, so it will not stay on {target} unless "
        f"the {html.escape(variable)} environment variable is set.",
        "Set it for your user account now? It takes effect for programs "
        "started after it is set; an already-open Setup &amp; Launcher must be "
        "reopened to pass it on. The last command below removes it by hand.",
    )


def close_message(target):
    """Return the message shown after a successful switch to ``target``; it
    holds even when closing MicroDrop is then refused."""
    return (
        f"The MicroDrop source is now on {target}. Close MicroDrop and start "
        f"MicroDrop again to run it."
    )


def still_running_warning(target):
    """Return the warning shown when MicroDrop did not close after switching
    to ``target``."""
    return (
        f"The MicroDrop source is now on {target}, but MicroDrop did not close "
        f"and is still running the previous version. Close MicroDrop and "
        f"start it again now."
    )


def skip_variable_failed_message(variable):
    """Return the PLAIN-text error for a ``variable`` that could not be
    saved, which stopped the switch."""
    return f"{variable} could not be set, so nothing was switched."


def switch_failed_message(target, variable=None):
    """Return the PLAIN-text error for a failed switch to ``target``;
    ``variable`` names the skip variable set just before it, if any."""
    text = f"Could not switch to {target}."

    if variable is not None:
        text += (
            f" {variable} is now set for your user account; the Remove button "
            f"in this dialog removes it."
        )

    return text


def check_failed_message():
    """Return the PLAIN-text message for a check for updates that failed;
    the dialog shows git's output, which says why, below it."""
    return (
        "Could not check for updates. If this computer is offline, check the "
        "internet connection and try again."
    )


def state_line(state, reason):
    """Return the PLAIN-text line explaining why versions cannot be switched
    in this checkout ``state``, or "" for a managed checkout. It is shown in
    a plain label, so ``reason`` goes in unescaped."""
    if state == DEVELOPMENT:
        return (
            f"This is a development checkout ({reason}): versions can be "
            f"browsed, not switched."
        )

    if state == NO_GIT:
        return f"Versions cannot be listed ({reason})."

    return ""


def skip_variable_line(variable):
    """Return the PLAIN-text line saying ``variable`` turns automatic updates
    off, for a plain label."""
    return f"Automatic updates are off because {variable} is set."


def newer_version_notice(tag_name):
    """Return the notice announcing release ``tag_name``."""
    return f"MicroDrop {tag_name} is available."
