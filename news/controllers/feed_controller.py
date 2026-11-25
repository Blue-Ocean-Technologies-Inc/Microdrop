# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Sci-Bots Feed's actions: load from the sources, push, remove, open.

Reload and push rule: the feed shows its sources' posts (the feed file,
the release notes) merged with the posts pushed this session, by id. A
push adds a post or replaces the one with its id, whether that came from a
source or an earlier push; pushed posts outlive every reload, so a source
post with a pushed id stays superseded by the push. Removing a post hides
its id for the session, until a push brings it back. Expired posts are
hidden. Every action reports in the model's status line; a bad post is
reported, and logged, without dropping the good ones.
"""

# Standard library imports.
import webbrowser
from functools import partial
from pathlib import Path
from typing import NamedTuple

# Enthought library imports.
from traits.api import Callable, Dict, Instance, List, Set, Str
from traitsui.api import Controller

# Local imports.
from ..models.feed_groups import group_posts
from ..models.feed_model import (
    ORIGIN_PUSHED,
    ORIGIN_SOURCE,
    FeedGroup,
    FeedPost,
    SciBotsFeed,
)
from ..models.feed_schema import is_web_url, parse_feed_payload
from ..services.feed_html import sanitise_summary_html
from ..services.feed_sources import FeedLoadError, IFeedSource, resolve_image_path

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Problems listed in the status line; the rest are only logged.
STATUS_MAX_PROBLEMS = 2


class PushResult(NamedTuple):
    """What a push did: ids added and updated, and one line per problem."""

    added: list
    updated: list
    errors: list


class LoadedFeed(NamedTuple):
    """The sources' posts as read (``read_feed_sources``): validated
    messages by id, one line per problem, and whether every source failed.
    Plain data, safe to hand from a worker thread to the GUI thread."""

    messages: dict
    problems: list
    all_failed: bool


def read_feed_sources(sources):
    """Read and validate every source's posts, their pictures resolved; on
    an id in several, the first source wins. A source that fails gives
    nothing and a problem. Qt-free and touches no shown model, so it may
    run on a worker thread."""
    messages, problems, failed = {}, [], 0

    for source in sources:
        try:
            payload = source.load()

        except FeedLoadError as error:
            problems.append(f"Feed source unavailable: {error}")
            failed += 1

            continue

        parsed = parse_feed_payload(payload)
        problems.extend(parsed.errors)

        for message in parsed.posts:
            messages.setdefault(
                message.id, with_resolved_pictures(message, source.resolve_image)
            )

    return LoadedFeed(messages, problems, bool(sources) and failed == len(sources))


def sort_posts(posts):
    """``posts`` pinned first, then newest first; ties keep their order."""
    return sorted(posts, key=lambda post: (not post.pinned, -post.date.toordinal()))


def feed_post_from_message(message, origin=ORIGIN_SOURCE):
    """The FeedPost a validated FeedPostMessage shows as; its summary_html
    sanitised."""
    return FeedPost(
        id=message.id,
        title=message.title,
        kind=message.kind,
        date=message.date,
        date_precision=message.date_precision,
        summary=message.summary,
        summary_html=sanitise_summary_html(message.summary_html),
        url=message.url,
        image=message.image,
        images=[(image.src, image.caption, image.alt) for image in message.images],
        pinned=message.pinned,
        source_label=message.source,
        expires=message.expires,
        origin=origin,
    )


def with_resolved_pictures(message, resolve):
    """``message`` with its picture paths passed through ``resolve``."""
    images = [
        image.model_copy(update={"src": resolve(image.src)}) for image in message.images
    ]

    return message.model_copy(
        update={"image": resolve(message.image), "images": images}
    )


def _plural(count, noun):
    return f"{count} {noun}{'' if count == 1 else 's'}"


class SciBotsFeedController(Controller):
    """Fills a SciBotsFeed from its source and from pushes."""

    #: The feed shown.
    model = Instance(SciBotsFeed, ())

    #: Where the feed's own posts come from; on an id in several, the
    #: first source wins.
    sources = List(Instance(IFeedSource))

    #: ``open_url(url)``: the system browser unless replaced.
    open_url = Callable(webbrowser.open)

    #: The source's posts as last loaded, by id.
    _source_messages = Dict(Str)

    #: The posts pushed this session, by id.
    _pushed_messages = Dict(Str)

    #: Ids removed this session.
    _removed_ids = Set(Str)

    # ------------------------------------------------------------------ #
    # Actions                                                             #
    # ------------------------------------------------------------------ #

    def reload(self):
        """Read every source again; pushed posts are kept. A source that
        fails contributes nothing and is reported; the others still load."""
        self.show_loaded(read_feed_sources(self.sources))

    def show_loaded(self, loaded):
        """Show the LoadedFeed read from the sources (``read_feed_sources``,
        perhaps on a worker); pushed posts are kept."""
        messages = loaded.messages

        self._source_messages = messages
        hidden = self._show_posts()

        # A clean load says nothing: the feed itself shows it.
        if not loaded.problems:
            logger.info(f"Sci-Bots Feed loaded {len(messages)} posts{hidden}")
            self.dismiss_status()

            return

        self._report(
            f"Loaded {_plural(len(messages), 'post')}{hidden}",
            loaded.problems,
            failed=loaded.all_failed,
        )

    def push(self, payload, base_dir=None):
        """Add or update the posts in ``payload`` (a post or a document, as
        a model, dict or JSON); relative image paths resolve against
        ``base_dir``. Returns a PushResult."""
        parsed = parse_feed_payload(payload)
        added, updated = [], []

        for message in parsed.posts:
            known = message.id in self._pushed_messages
            known = known or message.id in self._source_messages
            (updated if known else added).append(message.id)

            if base_dir is not None:
                message = with_resolved_pictures(
                    message, partial(resolve_image_path, base_dir=base_dir)
                )

            self._pushed_messages[message.id] = message
            self._removed_ids.discard(message.id)

        hidden = self._show_posts()
        outcome = (
            f"Pushed {_plural(len(added), 'new post')}, "
            f"{_plural(len(updated), 'update')}{hidden}"
        )

        if not parsed.posts:
            outcome = "Nothing pushed"

        self._report(outcome, parsed.errors)

        return PushResult(added, updated, parsed.errors)

    def push_file(self, path):
        """Push the post or document in the JSON file at ``path``."""
        path = Path(path)

        try:
            text = path.read_text(encoding="utf-8")

        except (OSError, ValueError) as error:
            self._report(f"Could not read {path.name}: {error}", [], failed=True)

            return PushResult([], [], [str(error)])

        return self.push(text, base_dir=path.parent)

    def remove(self, post_id):
        """Hide the post with ``post_id`` for the session."""
        self._pushed_messages.pop(post_id, None)
        self._removed_ids.add(post_id)
        self._show_posts()
        self._report("Removed 1 post", [])

    def open_post(self, post):
        """Open ``post``'s page in the browser; True if it was opened."""
        return self.open_link(post.url)

    def open_link(self, url):
        """Open ``url`` in the browser if it is http or https; True if so.
        Any other link is logged and ignored."""

        if not is_web_url(url):
            logger.warning(f"Not opening {url!r}: not an http or https URL")

            return False

        self.open_url(url)

        return True

    def toggle_expanded(self, post):
        """Show or hide the rest of ``post``'s summary."""
        post.expanded = not post.expanded

    def toggle_show_all(self, group):
        """Show all of ``group``'s posts, or only its first few again."""
        group.show_all = not group.show_all

    def dismiss_status(self):
        """Clear the status line."""
        self.model.trait_set(status_text="", status_is_error=False)

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _show_posts(self):
        """Merge source and pushed posts into the model; the note on hidden
        expired posts, or ""."""
        today = self.model.today()
        expanded = {post.id for post in self.model.posts if post.expanded}
        messages = {**self._source_messages, **self._pushed_messages}
        posts, expired = [], 0

        for post_id, message in messages.items():
            if post_id in self._removed_ids:
                continue

            if message.expires is not None and message.expires < today:
                expired += 1

                continue

            pushed = post_id in self._pushed_messages
            origin = ORIGIN_PUSHED if pushed else ORIGIN_SOURCE
            post = feed_post_from_message(message, origin)
            post.expanded = post_id in expanded
            posts.append(post)

        self.model.posts = sort_posts(posts)
        self._show_groups()

        return f" ({expired} expired, hidden)" if expired else ""

    def _show_groups(self):
        """Group the posts under their headers; a group keeps its Show all."""
        shown_all = {group.spec.id for group in self.model.groups if group.show_all}

        self.model.groups = [
            FeedGroup(spec=spec, posts=posts, show_all=spec.id in shown_all)
            for spec, posts in group_posts(self.model.posts)
        ]

    def _report(self, outcome, problems, failed=False):
        """Show ``outcome`` and the first problems in the status line; log
        every problem."""

        for problem in problems:
            logger.warning(f"Sci-Bots Feed: {problem}")

        lines = [outcome]

        if problems:
            lines[0] = f"{outcome}; {_plural(len(problems), 'problem')}:"
            lines.extend(problems[:STATUS_MAX_PROBLEMS])

        if len(problems) > STATUS_MAX_PROBLEMS:
            lines.append(f"… and {len(problems) - STATUS_MAX_PROBLEMS} more (see log)")

        self.model.trait_set(
            status_text="\n".join(lines), status_is_error=failed or bool(problems)
        )
