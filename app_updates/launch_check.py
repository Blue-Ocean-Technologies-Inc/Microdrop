# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The decision behind the background check after startup.

Pure: the plugin gathers the facts from git and the preferences, and acts on
what these functions return.
"""

# Microdrop utils imports.
from microdrop_utils.source_version import MANAGED, is_newer_release

# Local imports.
from .consts import ANNOUNCE, LOG_DOWNLOADED, NO_ACTION, POLICY_LATEST


def may_check(state, skip_variable_set):
    """Return True when the check may touch the checkout at all, fetching
    included: it is managed and the skip variable is unset."""
    return state == MANAGED and not skip_variable_set


def launch_check_action(
    state,
    skip_variable_set,
    policy,
    pending_tag,
    newest_panel_tag,
    current_release,
    last_announced,
):
    """Return what the check does, as ``(action, tag_name)``.

    Parameters
    ----------
    state, skip_variable_set
        The checkout state and whether the skip variable is set.
    policy
        POLICY_LATEST or POLICY_STAY.
    pending_tag
        The release the next start moves to, or None.
    newest_panel_tag
        The newest release with the Updates panel, or None.
    current_release
        The newest release HEAD is built on, or None.
    last_announced
        The release the user was last told about, or "".

    Returns
    -------
    ``(NO_ACTION, None)``, ``(LOG_DOWNLOADED, pending_tag)`` under
    POLICY_LATEST, or ``(ANNOUNCE, newest_panel_tag)`` under POLICY_STAY.
    """
    if not may_check(state, skip_variable_set):
        return NO_ACTION, None

    if policy == POLICY_LATEST:
        if pending_tag is None:
            return NO_ACTION, None

        return LOG_DOWNLOADED, pending_tag

    if newest_panel_tag is None or newest_panel_tag == last_announced:
        return NO_ACTION, None

    if not is_newer_release(newest_panel_tag, current_release):
        return NO_ACTION, None

    return ANNOUNCE, newest_panel_tag
