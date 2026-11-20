# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The state behind Help > "Check for Updates…": the release tags of the
source checkout, the update policy, and the version the action switches to.

Qt-free. ``refresh`` reads git and sets traits, so it runs on the GUI thread;
``fetch``, ``switch`` and the skip-variable writers set no traits and may run
off it.
"""

# Enthought library imports.
from traits.api import (
    Bool,
    Enum,
    HasTraits,
    Instance,
    List,
    Property,
    Str,
    observe,
)

# Microdrop utils imports.
from microdrop_utils.source_update_startup import (
    PROJECT_ROOT,
    SKIP_GIT_UPDATE_ENV_VAR,
    skip_variable_is_set,
)
from microdrop_utils.source_version import (
    HAS_PANEL,
    MANAGED,
    NO_GIT,
    SourceVersionError,
    changelog_section,
    checkout_state,
    current_release,
    describe,
    exact_release,
    fetch_tags,
    list_release_tags,
    newest_panel_tag,
    parse_release,
    switch_to,
)
from microdrop_utils.user_environment import (
    set_user_environment_variable,
    unset_user_environment_variable,
)

# Local imports.
from .consts import NO_CHANGELOG_TEXT, POLICY_LATEST, POLICY_STAY
from .preferences import AppUpdatesPreferences

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class VersionRow(HasTraits):
    """One release tag in the versions list."""

    #: The tag name, "v1.46.0".
    name = Str()

    #: The tag's creation date, "2026-11-18".
    date = Str()

    #: What the tag's tree holds: HAS_PANEL, FORCED_PULL or PLAIN.
    kind = Str()

    #: HEAD is exactly at this tag.
    is_current = Bool(False)

    #: The newest release with the Updates panel — what "latest" moves to.
    is_latest = Bool(False)

    #: The list's note on the row: "latest", "current", "no update panel",
    #: or several of them joined with ", ".
    marker = Property(Str, observe="is_latest, is_current, kind")

    def _get_marker(self):
        markers = []

        if self.is_latest:
            markers.append("latest")

        if self.is_current:
            markers.append("current")

        if self.kind != HAS_PANEL:
            markers.append("no update panel")

        return ", ".join(markers)


class UpdatesModel(HasTraits):
    """The source checkout's versions and the update policy."""

    #: The source checkout the dialog shows and moves.
    repo_root = Str(str(PROJECT_ROOT))

    #: Where the policy is saved.
    preferences = Instance(AppUpdatesPreferences)

    #: The backend runs in its own process, which a switch does not restart.
    frontend_only = Bool(False)

    #: The checkout state (MANAGED, DEVELOPMENT or NO_GIT) and why.
    state = Str()
    state_reason = Str()

    #: The checkout's version as git describes it: "v1.45.0", or
    #: "v1.46.0-3-gabc1234" between releases.
    current_description = Str()

    #: Every release tag, newest first; empty without git.
    versions = List(Instance(VersionRow))

    #: The row whose changelog is shown — and, under POLICY_STAY, the target.
    selected = Instance(VersionRow)

    #: Saved to the preferences the moment it changes.
    policy = Enum(POLICY_LATEST, POLICY_STAY)

    #: SKIP_GIT_UPDATE_ENV_VAR is set, so startup leaves the checkout alone.
    skip_variable_set = Bool(False)

    #: The selected release's changelog section.
    changelog_markdown = Str()

    #: The row the action switches to: the latest release under
    #: POLICY_LATEST, the selected row under POLICY_STAY.
    target = Property(Instance(VersionRow), observe="policy, selected, versions.items")

    #: The action button's caption.
    action_label = Property(Str, observe="target, _built_on_release")

    #: The action may run: the checkout is managed and the target is new.
    action_enabled = Property(Bool, observe="target, state, _built_on_release")

    #: The checkout may be moved.
    is_managed = Property(Bool, observe="state")

    #: The newest release HEAD is built on, "" when none is.
    _built_on_release = Str()

    # --- property getters ----------------------------------------------

    def _get_target(self):
        if self.policy == POLICY_STAY:
            return self.selected

        return next((row for row in self.versions if row.is_latest), None)

    def _get_action_label(self):
        if not self._target_is_new():
            return "Up to date"

        return f"Switch to {self.target.name} and close"

    def _get_action_enabled(self):
        return self.is_managed and self._target_is_new()

    def _get_is_managed(self):
        return self.state == MANAGED

    # --- public methods -------------------------------------------------

    def refresh(self):
        """Re-read the checkout and the preferences; keep the selected row by
        name, else select the current one."""
        self.state, self.state_reason = checkout_state(self.repo_root)
        self.skip_variable_set = skip_variable_is_set()
        self._read_policy()

        if self.state == NO_GIT:
            self.current_description = ""
            self._built_on_release = ""
            self.versions = []
            self.selected = None

            return

        self.current_description = describe(self.repo_root)
        self._built_on_release = current_release(self.repo_root) or ""

        tags = list_release_tags(self.repo_root)
        latest = newest_panel_tag(tags)
        exact = exact_release(self.repo_root)
        selected_name = self.selected.name if self.selected else None

        self.versions = [
            VersionRow(
                name=tag.name,
                date=tag.date,
                kind=tag.kind,
                is_current=tag.name == exact,
                is_latest=tag == latest,
            )
            for tag in tags
        ]

        self.selected = next(
            (row for row in self.versions if row.name == selected_name),
            next((row for row in self.versions if row.is_current), None),
        )

    def fetch(self):
        """Fetch the release tags of ``origin``; the caller refreshes after.
        Raises SourceVersionError when the checkout is not managed or the
        fetch fails."""
        self._require_managed("fetch tags")
        fetch_tags(self.repo_root)

    def switch(self):
        """Check out the target release. Raises SourceVersionError when the
        checkout is not managed, there is no target, or git refuses."""
        target = self.target

        if target is None:
            raise SourceVersionError("There is no version to switch to")

        self._require_managed(f"switch to {target.name}")

        logger.info(f"Switching the MicroDrop source to {target.name}")
        switch_to(self.repo_root, target.name)

    def drops_unreleased_commits(self):
        """Return True when HEAD is past its release and the target is not
        newer — switching leaves the unreleased commits behind."""
        if self.target is None or not self._built_on_release:
            return False

        if any(row.is_current for row in self.versions):
            return False

        return parse_release(self.target.name) <= parse_release(self._built_on_release)

    def set_skip_variable(self):
        """Save SKIP_GIT_UPDATE_ENV_VAR for the user; may block for seconds.
        ``skip_variable_set`` follows at the next ``refresh``."""
        set_user_environment_variable(SKIP_GIT_UPDATE_ENV_VAR, "1")

    def clear_skip_variable(self):
        """Remove SKIP_GIT_UPDATE_ENV_VAR for the user; may block for
        seconds. ``skip_variable_set`` follows at the next ``refresh``."""
        unset_user_environment_variable(SKIP_GIT_UPDATE_ENV_VAR)

    # --- observers ------------------------------------------------------

    @observe("preferences")
    def _policy_from_preferences(self, event):
        self._read_policy()

    @observe("policy")
    def _save_policy(self, event):
        auto_update = self.policy == POLICY_LATEST

        if self.preferences is None or self.preferences.auto_update == auto_update:
            return

        self.preferences.auto_update = auto_update
        self.preferences.preferences.flush()

    @observe("selected")
    def _show_selected_changelog(self, event):
        if self.selected is None:
            self.changelog_markdown = ""

            return

        self.changelog_markdown = (
            changelog_section(self.repo_root, self.selected.name) or NO_CHANGELOG_TEXT
        )

    # --- helpers --------------------------------------------------------

    def _read_policy(self):
        if self.preferences is not None:
            self.policy = POLICY_LATEST if self.preferences.auto_update else POLICY_STAY

    def _target_is_new(self):
        """Return True when switching to the target would change the
        checkout: under POLICY_LATEST, only to a newer release."""
        target = self.target

        if target is None or target.is_current:
            return False

        if self.policy == POLICY_STAY:
            return True

        # A checkout built on no release is older than any.
        built_on = parse_release(self._built_on_release) or (0, 0, 0)

        return parse_release(target.name) > built_on

    def _require_managed(self, action):
        """Raise SourceVersionError unless the checkout is managed now — it
        may have changed since the last refresh."""
        state, reason = checkout_state(self.repo_root)

        if state != MANAGED:
            raise SourceVersionError(
                f"Cannot {action}: the source checkout is not managed ({reason})"
            )
