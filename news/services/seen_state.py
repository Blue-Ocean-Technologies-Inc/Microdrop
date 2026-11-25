# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""What the user has already seen of the news, across launches. Qt-free.

A small JSON file in the notifications data folder, written only by the
news plugin and the moment it changes: ``preferences.ini`` is rewritten by every
process when it stops, which would undo a change made meanwhile. It holds
the ids of the posts already seen and the last MicroDrop version whose
release notes were shown.

The release notes used to be shown by a dialog at launch, which kept the
CHANGELOG.md text it last showed in ``.previous_changelog``. On a first run
the state starts from that cache: a version whose notes it already holds
counts as shown.
"""

# Standard library imports.
import re
from pathlib import Path

# Enthought library imports.
from traits.api import Bool, File, HasTraits, Set, Str

# Microdrop utils imports.
from microdrop_utils.json_state_file import read_json_state, write_json_state

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The state file's keys.
SEEN_POST_IDS_KEY = "seen_post_ids"
RELEASE_NOTES_SHOWN_KEY = "release_notes_shown_version"


def changelog_has_version(changelog_text, version):
    """Whether ``changelog_text`` holds a release heading for ``version``,
    e.g. "## v1.50.0 (2026-11-20)"."""
    heading = re.compile(rf"^#+\s*v?{re.escape(version)}\b", re.MULTILINE)

    return bool(heading.search(changelog_text))


class NewsSeenState(HasTraits):
    """The posts seen and the release notes shown, saved as they change."""

    #: The state file; nothing is read or written while empty.
    path = File()

    #: Ids of the posts the user has seen.
    seen_post_ids = Set(Str)

    #: The last version whose release notes were shown; "" when none.
    release_notes_shown_version = Str()

    #: Whether the file existed when loaded: a first run when not.
    existed = Bool(False)

    #: CHANGELOG.md, and the What's New dialog's cache of the text it last
    #: showed: kept current as notes are shown here, so a plugin selection
    #: without the news plugin does not show them again.
    changelog_path = File()
    previous_changelog_path = File()

    def load(self, release_version=""):
        """Read the file. On a first run, take the release notes the old
        dialog already showed (its cache) as shown for ``release_version``.
        A file that cannot be read starts the state empty."""
        path = Path(self.path)
        self.existed = path.is_file()

        if not self.existed:
            self._migrate(self.previous_changelog_path, release_version)

            return

        data = read_json_state(path)

        if data is None:
            return

        self.seen_post_ids = set(data.get(SEEN_POST_IDS_KEY, []))
        self.release_notes_shown_version = str(data.get(RELEASE_NOTES_SHOWN_KEY, ""))

    def is_seen(self, post_id):
        return post_id in self.seen_post_ids

    def mark_seen(self, post_ids, release_version=""):
        """Record ``post_ids`` as seen (and the release notes of
        ``release_version`` as shown); saved at once when anything changed."""
        added = set(post_ids) - self.seen_post_ids
        version_changed = release_version and (
            release_version != self.release_notes_shown_version
        )

        if not added and not version_changed:
            return

        self.seen_post_ids = self.seen_post_ids | added

        if version_changed:
            self.release_notes_shown_version = release_version
            self._refresh_previous_changelog()

        self.save()

    def save(self):
        """Write the state file, replacing it whole."""

        if not self.path:
            return

        data = {
            SEEN_POST_IDS_KEY: sorted(self.seen_post_ids),
            RELEASE_NOTES_SHOWN_KEY: self.release_notes_shown_version,
        }
        write_json_state(self.path, data)

    def _refresh_previous_changelog(self):

        if not self.changelog_path or not self.previous_changelog_path:
            return

        try:
            text = Path(self.changelog_path).read_text(encoding="utf-8")
            Path(self.previous_changelog_path).write_text(text, encoding="utf-8")

        except OSError as error:
            logger.error(f"Could not refresh {self.previous_changelog_path}: {error}")

    def _migrate(self, previous_changelog, release_version):

        if not previous_changelog or not release_version:
            return

        try:
            text = Path(previous_changelog).read_text(encoding="utf-8")

        except OSError:
            return

        if changelog_has_version(text, release_version):
            self.release_notes_shown_version = release_version
