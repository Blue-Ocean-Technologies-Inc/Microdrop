# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Read and write feed files for the feed creator. Qt-free.

A saved file is a FeedDocument: ``$schema``, ``version``, ``_readme`` if
any, then the posts, each with its id and only the fields it sets, keys
always in the same order, pretty-printed UTF-8, so a repo diff shows only
what changed. Writes go to a temporary file that then replaces the target,
so a failed save never leaves half a file.
"""

# Standard library imports.
import json
import os
import tempfile
from pathlib import Path

# Local imports.
from ..models.feed_schema import (
    FEED_SCHEMA_VERSION,
    PRECISION_MONTH,
    SCHEMA_PATH,
    parse_feed_payload,
)
from .model import EditablePost

#: A post's keys in the order they are written.
POST_KEY_ORDER = (
    "id",
    "title",
    "kind",
    "date",
    "source",
    "pinned",
    "summary",
    "summary_html",
    "url",
    "image",
    "images",
    "expires",
)


def editable_from_message(message):
    """The form's EditablePost for a validated FeedPostMessage."""
    return EditablePost(
        id=message.id,
        title=message.title,
        kind=message.kind,
        date=message.date,
        month_only=message.date_precision == PRECISION_MONTH,
        summary=message.summary,
        summary_html=message.summary_html,
        url=message.url,
        image=message.image,
        images=[image.model_dump(exclude_defaults=True) for image in message.images],
        pinned=message.pinned,
        source=message.source,
        has_expires=message.expires is not None,
        expires=message.expires or message.date,
    )


def post_data(post):
    """``post`` as feed-file JSON data: its id, the fields it sets, in
    POST_KEY_ORDER."""
    values = {
        "id": post.id,
        "title": post.title,
        "kind": post.kind,
        "date": post.date.strftime("%Y-%m" if post.month_only else "%Y-%m-%d"),
        "source": post.source,
        "pinned": post.pinned,
        "summary": post.summary,
        "summary_html": post.summary_html,
        "url": post.url,
        "image": post.image,
        "images": post.images if len(post.images) > 1 else [],
        "expires": post.expires.isoformat() if post.has_expires else None,
    }

    return {
        key: values[key]
        for key in POST_KEY_ORDER
        if values[key] not in ("", False, None, [])
    }


def schema_reference(path):
    """How a feed file at ``path`` names the JSON Schema: relative if it
    can be, so the file and schema can move together."""

    try:
        relative = os.path.relpath(SCHEMA_PATH, Path(path).resolve().parent)

    except ValueError:
        # On another drive there is no relative path.
        return SCHEMA_PATH.as_uri()

    return f"./{Path(relative).as_posix()}"


def document_text(posts, path, readme=""):
    """The feed file text for ``posts`` saved at ``path``."""
    document = {"$schema": schema_reference(path), "version": FEED_SCHEMA_VERSION}

    if readme:
        document["_readme"] = readme

    document["posts"] = [post_data(post) for post in posts]

    return f"{json.dumps(document, indent=2, ensure_ascii=False)}\n"


def write_atomically(path, text):
    """Write ``text`` to ``path`` as UTF-8 through a temporary file in the
    same folder that then replaces it."""
    path = Path(path)
    handle, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )

    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as file:
            file.write(text)

        os.replace(temporary, path)

    except BaseException:
        Path(temporary).unlink(missing_ok=True)

        raise


def read_feed_file(path):
    """The posts, readme and problems of the feed file at ``path``: the good
    posts load, a bad one is a problem line. Raises OSError if unreadable."""
    text = Path(path).read_text(encoding="utf-8")
    parsed = parse_feed_payload(text)
    readme = ""

    try:
        data = json.loads(text)

    except json.JSONDecodeError:
        data = None

    if isinstance(data, dict):
        readme = str(data.get("_readme", ""))

    posts = [editable_from_message(message) for message in parsed.posts]

    return posts, readme, parsed.errors
