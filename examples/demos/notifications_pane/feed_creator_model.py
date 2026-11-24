# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free state of the feed creator: the feed file being written, the post
being edited, the checks on them and the preview.

State only: FeedCreatorController validates, sorts, saves and pushes.
"""

# Standard library imports.
import datetime

# Enthought library imports.
from traits.api import (
    Bool,
    Button,
    Date,
    Enum,
    File,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    Str,
)

# Local imports.
from .sci_bots_feed_model import SciBotsFeed
from .sci_bots_feed_schema import FEED_KINDS

#: The post fields an author edits; a change to any marks the file changed.
EDITABLE_FIELDS = (
    "title",
    "kind",
    "date",
    "month_only",
    "summary",
    "summary_html",
    "url",
    "image",
    "pinned",
    "source",
    "has_expires",
    "expires",
)

#: How bad a check is: an error blocks saving, a warning does not.
CHECK_ERROR = "Error"
CHECK_WARNING = "Warning"

#: How the preview is themed.
PREVIEW_THEMES = ("Current theme", "Light", "Dark")


class EditablePost(HasTraits):
    """One post as the form edits it."""

    #: Stable id, kept once given; a new post gets one when first saved.
    id = Str()

    title = Str()

    kind = Enum(*FEED_KINDS)

    date = Date(datetime.date.today())

    #: Only the month is known: saved as "2026-09", shown "September 2026".
    month_only = Bool(False)

    #: Plain text, kept in step with summary_html by the controller.
    summary = Str()

    #: The rich summary as the editor writes it, sanitised.
    summary_html = Str()

    url = Str()

    #: A file path or an https address.
    image = Str()

    pinned = Bool(False)

    source = Str()

    #: Whether the post is hidden after ``expires``.
    has_expires = Bool(False)

    expires = Date(datetime.date.today())

    #: The fields the last check found wrong, e.g. ["url"].
    invalid_fields = List(Str)

    #: Per field, whether the form marks it wrong.
    title_invalid = Property(Bool, observe="invalid_fields")
    kind_invalid = Property(Bool, observe="invalid_fields")
    date_invalid = Property(Bool, observe="invalid_fields")
    url_invalid = Property(Bool, observe="invalid_fields")
    image_invalid = Property(Bool, observe="invalid_fields")

    #: A plain-language note under the picture field, or "".
    image_hint = Property(Str, observe="image")

    #: The post list's columns: "★ Newsletter · MicroTAS…" and "2026-09".
    list_title = Property(Str, observe="[title, kind, pinned]")
    list_date = Property(Str, observe="[date, month_only]")

    def _get_title_invalid(self):
        return "title" in self.invalid_fields

    def _get_kind_invalid(self):
        return "kind" in self.invalid_fields

    def _get_date_invalid(self):
        return "date" in self.invalid_fields

    def _get_url_invalid(self):
        return "url" in self.invalid_fields

    def _get_image_invalid(self):
        return "image" in self.invalid_fields

    def _get_image_hint(self):
        if not self.image or self.image.startswith("https://"):
            return ""

        return (
            "This picture is a file on this computer. Readers' computers will "
            "not have it: before publishing, use a web address (https://…)."
        )

    def _get_list_title(self):
        pin = "★ " if self.pinned else ""

        return f"{pin}{self.kind.title()} · {self.title or '(no title)'}"

    def _get_list_date(self):
        return self.date.strftime("%Y-%m" if self.month_only else "%Y-%m-%d")


class FeedCheck(HasTraits):
    """One problem found in the feed file."""

    #: CHECK_ERROR blocks saving; CHECK_WARNING does not.
    severity = Enum(CHECK_ERROR, CHECK_WARNING)

    #: The post it is about, or None for the file as a whole.
    post = Instance(EditablePost)

    #: In plain language, e.g. "Post 3 'MicroTAS…': the link must …".
    text = Str()


class FeedCreatorModel(HasTraits):
    """The feed file being written."""

    #: Where it was opened from or last saved to; "" for a new file.
    path = File()

    #: A note to the file's authors, kept as it was read.
    readme = Str()

    #: The posts, pinned first then newest first, as the feed shows them.
    posts = List(Instance(EditablePost))

    #: The post the form edits.
    selected = Instance(EditablePost)

    #: Whether there are changes not saved yet.
    dirty = Bool(False)

    #: The problems found, errors first.
    checks = List(Instance(FeedCheck))

    #: The checks as the list shows them, e.g. "Error — Post 3 'Micro…': …".
    check_lines = Property(List(Str), observe="checks.items")

    #: The row selected in the checks list; selecting one selects its post.
    selected_check_index = Int(-1)

    #: Whether a check blocks saving.
    has_errors = Property(Bool, observe="checks.items")

    #: One line over the checks, e.g. "1 error, 2 warnings".
    checks_summary = Property(Str, observe="checks.items")

    #: The window title, with "*" while there are unsaved changes.
    title = Property(Str, observe="path, dirty")

    #: The edited post as the feed would show it.
    preview = Instance(SciBotsFeed, ())

    #: How the preview is themed.
    preview_theme = Enum(*PREVIEW_THEMES)

    #: Whether "Send to demo feed" has a feed to send to.
    can_send = Bool(False)

    #: What the last save or send did.
    status = Str()

    new_button = Button("New")
    open_button = Button("Open…")
    save_button = Button("Save")
    save_as_button = Button("Save As…")
    send_button = Button("Send to demo feed")

    add_button = Button("Add")
    duplicate_button = Button("Duplicate")
    delete_button = Button("Delete")

    def _get_check_lines(self):
        return [f"{check.severity} — {check.text}" for check in self.checks]

    def _get_has_errors(self):
        return any(check.severity == CHECK_ERROR for check in self.checks)

    def _get_checks_summary(self):
        errors = sum(check.severity == CHECK_ERROR for check in self.checks)
        warnings = len(self.checks) - errors

        if not self.checks:
            return "All checks passed."

        parts = []

        if errors:
            parts.append(f"{errors} error{'s' if errors > 1 else ''} (fix to save)")

        if warnings:
            parts.append(f"{warnings} warning{'s' if warnings > 1 else ''}")

        return ", ".join(parts)

    def _get_title(self):
        name = self.path.replace("\\", "/").rsplit("/", 1)[-1] or "New feed"

        return f"{'*' if self.dirty else ''}{name} — Sci-Bots Feed creator"
