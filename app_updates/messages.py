# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The texts of the updates dialogs, as HTML message bodies.

Version names are ``vX.Y.Z`` and go in as they are; every other value is
escaped, so a path or a command is never taken as markup.
"""

# Standard library imports.
import html

# Microdrop utils imports.
from microdrop_utils.source_version import DEFAULT_BRANCH, DEVELOPMENT, NO_GIT


def _paragraphs(*paragraphs):
    return "<br><br>".join(paragraphs)


def _command_block(commands):
    return f"<pre>{html.escape(commands)}</pre>"


def _no_panel_paragraphs(target, commands):
    return (
        f"{target} has no Updates panel, so MicroDrop cannot bring you back "
        f"from inside the app.",
        f"To return to the latest version, use the Setup &amp; Launcher, or "
        f"run these commands:{_command_block(commands)}",
    )


def plain_confirmation(target, drops_unreleased, frontend_only):
    """Return the confirmation for switching to a release with the Updates
    panel."""
    paragraphs = [f"Switch MicroDrop to {target}? MicroDrop closes once it is done."]

    if drops_unreleased:
        paragraphs.append(
            f"You are running unreleased commits made after the last release; "
            f"{target} does not include them."
        )

    if frontend_only:
        paragraphs.append(
            f"The backend runs separately: restart the backend too, so it also "
            f"runs {target}."
        )

    return _paragraphs(*paragraphs)


def no_panel_warning(target, commands):
    """Return the warning for switching to a release without the Updates
    panel; ``commands`` are the shell lines that return the checkout."""
    return _paragraphs(
        *_no_panel_paragraphs(target, commands),
        f"Switch to {target} anyway?",
    )


def forced_pull_warning(target, commands, variable, unset_command):
    """Return the warning for switching to a release that pulls ``main`` at
    every start unless ``variable`` is set; ``unset_command`` removes the
    variable by hand."""
    return _paragraphs(
        *_no_panel_paragraphs(target, commands),
        f"{target} also updates itself: at its next start it checks out "
        f"{DEFAULT_BRANCH} and pulls, so it will not stay on {target} unless "
        f"the {html.escape(variable)} environment variable is set.",
        "Set it for your user account now? It takes effect for programs "
        "started after it is set; an already-open Setup &amp; Launcher must be "
        "reopened to pass it on.",
        f"To remove it by hand later, run:{_command_block(unset_command)}",
    )


def close_message(target):
    """Return the message shown after a successful switch to ``target``."""
    return (
        f"MicroDrop switched to {target} and will now close; start MicroDrop "
        f"again to run it."
    )


def state_line(state, reason):
    """Return the line explaining why versions cannot be switched in this
    checkout ``state``, or "" for a managed checkout."""
    if state == DEVELOPMENT:
        return (
            f"This is a development checkout ({html.escape(reason)}): versions "
            f"can be browsed, not switched."
        )

    if state == NO_GIT:
        return f"Versions cannot be listed ({html.escape(reason)})."

    return ""


def skip_variable_line(variable):
    """Return the line saying ``variable`` turns automatic updates off."""
    return f"Automatic updates are off because {html.escape(variable)} is set."


def newer_version_notice(tag_name):
    """Return the notice announcing release ``tag_name``."""
    return f"MicroDrop {tag_name} is available."
