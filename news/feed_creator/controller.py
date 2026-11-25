# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The feed creator's actions: file New/Open/Save, post Add/Duplicate/
Delete, the checks, the live preview, and Send to demo feed.

Checks are the feed's own FeedPostMessage validation, worded for authors;
errors block saving, warnings do not. A file with bad posts still opens:
its good posts load and the bad ones are listed, and left out on save.
"""

# Standard library imports.
from pathlib import Path

# Enthought library imports.
from traits.api import Any, Instance, List, Str, observe
from traitsui.api import Controller

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import (
    YES,
    confirm,
    file_dialog,
    warning,
)

# Local imports.
from ..controllers.feed_controller import sort_posts
from ..models.feed_model import FeedPost
from ..models.feed_schema import (
    PRECISION_DAY,
    PRECISION_MONTH,
    derive_post_id,
)
from ..services.feed_html import html_to_plain_text, sanitise_summary_html
from ..services.feed_sources import resolve_image_path
from .checks import feed_checks
from .io import (
    document_text,
    post_data,
    read_feed_file,
    write_atomically,
)
from .model import (
    EDITABLE_FIELDS,
    EditablePost,
    FeedCreatorModel,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

JSON_WILDCARD = "Feed files (*.json)"

#: The edits that move a post in the list.
_ORDER_FIELDS = ("pinned", "date", "month_only")


class FeedCreatorController(Controller):
    """Acts on a FeedCreatorModel; optionally sends to a demo feed."""

    #: The file being written.
    model = Instance(FeedCreatorModel, ())

    #: The feed's SciBotsFeedController "Send to demo feed" pushes to; None
    #: when the creator runs on its own.
    feed_controller = Any()

    #: Problems of the posts that could not be read from the opened file.
    _load_problems = List(Str)

    def init(self, info):
        """Show the first check results and the window title."""
        self.check()
        self._show_window_title()

        return True

    def close(self, info, is_ok):
        """Ask before discarding unsaved changes."""
        return self._may_discard("close")

    # ------------------------------------------------------------------ #
    # File actions                                                        #
    # ------------------------------------------------------------------ #

    def new_document(self):
        """Start an empty feed file."""
        self._load_problems = []
        self.model.trait_set(path="", readme="", posts=[], selected=None)
        self.model.dirty = False
        self.check()

    def open_file(self, path):
        """Open the feed file at ``path``: its good posts, its bad ones as
        checks. True if it was read."""

        try:
            posts, readme, problems = read_feed_file(path)

        except (OSError, ValueError) as error:
            logger.error(f"Feed creator could not open {path}: {error}")
            warning(self._parent(), f"Could not open {path}:\n{error}", cancel=False)

            return False

        self._load_problems = problems
        posts = sort_posts(posts)
        self.model.trait_set(
            path=str(path),
            readme=readme,
            posts=posts,
            selected=posts[0] if posts else None,
        )
        self.model.dirty = False
        self.check()

        return True

    def save(self):
        """Save to the file's path, asking for one if it has none."""

        if not self.model.path:
            return self.save_as()

        return self._write(self.model.path)

    def save_as(self):
        """Save under a path the author chooses."""
        path = file_dialog(
            parent=self._parent(),
            action="save",
            default_path=self.model.path,
            wildcard=JSON_WILDCARD,
        )

        if not path:
            return False

        if not path.lower().endswith(".json"):
            path = f"{path}.json"

        return self._write(path)

    def send_to_feed(self):
        """Push the file's posts into the demo feed, as they would arrive."""

        if self.feed_controller is None:
            return

        self._give_ids()
        base_dir = Path(self.model.path).parent if self.model.path else None
        payload = {"posts": [post_data(post) for post in self.model.posts]}
        result = self.feed_controller.push(payload, base_dir=base_dir)

        self.model.status = (
            f"Sent to the demo feed: {len(result.added)} new, "
            f"{len(result.updated)} updated, {len(result.errors)} not accepted."
        )

    # ------------------------------------------------------------------ #
    # Checks                                                              #
    # ------------------------------------------------------------------ #

    def check(self):
        """Check every post against the feed's rules; errors first."""
        self.model.checks = feed_checks(self.model.posts, self._load_problems)

    # ------------------------------------------------------------------ #
    # Reactions                                                           #
    # ------------------------------------------------------------------ #

    @observe("model:new_button")
    def _new_clicked(self, event):
        if self._may_discard("start a new feed"):
            self.new_document()

    @observe("model:open_button")
    def _open_clicked(self, event):
        if not self._may_discard("open another feed"):
            return

        path = file_dialog(
            parent=self._parent(), default_path=self.model.path, wildcard=JSON_WILDCARD
        )

        if path:
            self.open_file(path)

    @observe("model:save_button")
    def _save_clicked(self, event):
        self.save()

    @observe("model:save_as_button")
    def _save_as_clicked(self, event):
        self.save_as()

    @observe("model:send_button")
    def _send_clicked(self, event):
        self.send_to_feed()

    @observe("model:add_button")
    def _add_clicked(self, event):
        self._insert(EditablePost())

    @observe("model:duplicate_button")
    def _duplicate_clicked(self, event):
        selected = self.model.selected

        if selected is not None:
            copy = selected.clone_traits(traits=list(EDITABLE_FIELDS))
            copy.title = f"{selected.title} (copy)"
            self._insert(copy)

    @observe("model:delete_button")
    def _delete_clicked(self, event):
        selected = self.model.selected

        if selected is None:
            return

        index = self.model.posts.index(selected)
        self.model.posts.remove(selected)
        remaining = self.model.posts
        self.model.selected = (
            remaining[min(index, len(remaining) - 1)] if remaining else None
        )

    @observe("model:selected_check_index")
    def _select_checked_post(self, event):
        checks = self.model.checks

        if 0 <= event.new < len(checks) and checks[event.new].post is not None:
            self.model.selected = checks[event.new].post

    @observe("model:posts:items:[" + ", ".join(EDITABLE_FIELDS) + "]")
    def _post_edited(self, event):
        if event.name == "summary_html":
            event.object.summary = html_to_plain_text(event.new)

        # A browsed picture file, kept relative to the feed file if below it.
        if event.name == "image" and Path(event.new).is_absolute():
            relative = self._relative_to_feed(event.new)

            if relative != event.new:
                event.object.image = relative

                return

        if event.name in _ORDER_FIELDS:
            self._sort_keeping_selection()

        self.model.dirty = True
        self.check()
        self._update_preview()

    @observe("model:posts:items")
    def _posts_changed(self, event):
        self.model.dirty = True
        self.check()

    @observe("model:selected")
    def _selected_changed(self, event):
        self._update_preview()

    @observe("model:title")
    def _show_window_title(self, event=None):
        if self.info is not None and self.info.ui is not None:
            self.info.ui.control.setWindowTitle(self.model.title)

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _insert(self, post):
        self.model.posts.append(post)
        self._sort_keeping_selection()
        self.model.selected = post

    def _sort_keeping_selection(self):
        ordered = sort_posts(self.model.posts)

        if ordered != self.model.posts:
            selected = self.model.selected
            self.model.posts = ordered
            self.model.selected = selected

    def _update_preview(self):
        """Show the edited post as the feed would, as readers first see it."""
        post = self.model.selected

        if post is None:
            self.model.preview.posts = []

            return

        base_dir = Path(self.model.path).parent if self.model.path else Path.cwd()
        self.model.preview.posts = [
            FeedPost(
                id=post.id,
                title=post.title or "(no title yet)",
                kind=post.kind,
                date=post.date,
                date_precision=PRECISION_MONTH if post.month_only else PRECISION_DAY,
                summary=post.summary,
                summary_html=sanitise_summary_html(post.summary_html),
                url=post.url,
                image=resolve_image_path(post.image, base_dir),
                pinned=post.pinned,
                source_label=post.source,
            )
        ]

    def _give_ids(self):
        """Give every post without an id one, kept from then on."""

        for post in self.model.posts:
            if not post.id:
                post.id = derive_post_id(post.url, post.title)

    def _write(self, path):
        """Check, then save atomically to ``path``; True if saved."""
        self.check()

        if self.model.has_errors:
            warning(
                self._parent(),
                "Fix the errors listed under Checks before saving.",
                title="Not saved",
                cancel=False,
            )

            return False

        if self._load_problems:
            message = (
                f"{len(self._load_problems)} problem(s) in the opened file could "
                "not be read; those posts will be left out. Save anyway?"
            )

            if confirm(self._parent(), message, title="Save") != YES:
                return False

        self._give_ids()

        try:
            text = document_text(self.model.posts, path, self.model.readme)
            write_atomically(path, text)

        except OSError as error:
            logger.error(f"Feed creator could not save {path}: {error}")
            warning(self._parent(), f"Could not save:\n{error}", cancel=False)

            return False

        self._load_problems = []
        self.model.trait_set(path=str(path), dirty=False, status=f"Saved {path}")
        self.check()

        return True

    def _may_discard(self, action):
        """Whether unsaved changes may go, asking the author if there are
        any."""

        if not self.model.dirty:
            return True

        message = f"The feed has unsaved changes. Discard them and {action}?"

        return confirm(self._parent(), message, title="Unsaved changes") == YES

    def _relative_to_feed(self, path):
        """``path`` relative to the feed file's folder when below it."""

        if not self.model.path:
            return path

        folder = Path(self.model.path).resolve().parent

        try:
            return Path(path).resolve().relative_to(folder).as_posix()

        except ValueError:
            return path

    def _parent(self):
        if self.info is not None and self.info.ui is not None:
            return self.info.ui.control

        return None
