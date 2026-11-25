# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!


"""The feed creator's checks, Qt-free: each post against the feed's rules
(its schema, plus advice such as an https:// picture), and posts that
would replace one another."""

# Third-party imports.
from pydantic import ValidationError

# Local imports.
from ..models.feed_schema import FeedPostMessage, derive_post_id, validation_problems
from .io import post_data
from .model import CHECK_ERROR, CHECK_WARNING, FeedCheck

#: How a check names a field.
FIELD_LABELS = {
    "title": "the title",
    "kind": "the type",
    "date": "the date",
    "url": "the link",
    "image": "the picture",
    "summary": "the summary",
    "summary_html": "the summary",
    "source": "the source",
    "expires": "the end date",
}

#: Characters of a title quoted in a check.
CHECK_TITLE_CHARS = 30

#: Kinds that need no summary: their card stands on title and picture.
KINDS_WITHOUT_SUMMARY = ("newsletter", "release")


def post_name(number, post):
    title = post.title or "(no title)"

    if len(title) > CHECK_TITLE_CHARS:
        title = f"{title[:CHECK_TITLE_CHARS].rstrip()}…"

    return f"Post {number} '{title}'"


def feed_checks(posts, load_problems=()):
    """Every post checked against the feed's rules, errors first; each
    post's ``invalid_fields`` set from its errors."""
    checks = []
    ids = {}

    for number, post in enumerate(posts, start=1):
        name = post_name(number, post)
        post.invalid_fields = []

        for severity, field, text in post_problems(post):
            label = FIELD_LABELS.get(field, "")
            checks.append(
                FeedCheck(
                    severity=severity,
                    post=post,
                    text=f"{name}: {label} {text}".replace("  ", " "),
                )
            )

            if severity == CHECK_ERROR and field:
                post.invalid_fields.append(field)

        post_id = post.id or derive_post_id(post.url, post.title)

        if post_id in ids:
            checks.append(
                FeedCheck(
                    severity=CHECK_ERROR,
                    post=post,
                    text=f"{name}: has the same title and link as post "
                    f"{ids[post_id]}; one would replace the other.",
                )
            )

        ids.setdefault(post_id, number)

    for problem in load_problems:
        checks.append(
            FeedCheck(
                severity=CHECK_WARNING,
                text=f"Could not be read, so it is left out when saving: {problem}",
            )
        )

    return sorted(checks, key=lambda check: check.severity)


def post_problems(post):
    """``(severity, field, text)`` for each problem with ``post``."""
    problems = []

    try:
        FeedPostMessage.model_validate(post_data(post))

    except ValidationError as error:
        problems.extend(
            (CHECK_ERROR, field, text) for field, text in validation_problems(error)
        )

    no_summary = not post.summary and not post.summary_html

    if no_summary and post.kind not in KINDS_WITHOUT_SUMMARY:
        problems.append((CHECK_WARNING, "summary", "is empty."))

    if post.image and not post.image.startswith("https://"):
        problems.append(
            (
                CHECK_WARNING,
                "image",
                "is a file on this computer; a hosted feed needs a web "
                "address (https://…) for it.",
            )
        )

    if post.url.startswith("http://"):
        problems.append(
            (CHECK_WARNING, "url", "is not secure (http://); prefer https://.")
        )

    if post.has_expires and post.expires < post.date:
        problems.append((CHECK_WARNING, "expires", "is before the post's date."))

    return problems
