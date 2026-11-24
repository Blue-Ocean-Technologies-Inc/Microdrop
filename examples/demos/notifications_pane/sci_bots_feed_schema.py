# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Sci-Bots Feed's input contract: one post (FeedPostMessage) or a whole
feed file (FeedDocument), shaped like ``notifications.consts`` payloads so it
can become a validated topic contract unchanged.

Strict where it protects the user — an unknown ``kind``, a non-web ``url``
or a missing ``title`` is rejected — and lenient where it helps authors:
unknown keys are ignored with a log note. parse_feed_payload validates post
by post, so one bad post never drops the good ones, and says what is wrong
with each bad one in a single line.

The JSON Schema editors use is generated from these models::

    pixi run python -m examples.demos.notifications_pane.sci_bots_feed_schema
"""

# Standard library imports.
import datetime
import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal, NamedTuple
from urllib.parse import urlparse

# Third-party imports.
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    WithJsonSchema,
    field_validator,
    model_validator,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The feed file format this module reads.
FEED_SCHEMA_VERSION = 1

#: What a post is.
FEED_KINDS = ("announcement", "product", "newsletter", "post", "release")

#: How exactly a post's date is known: its day, or only its month.
PRECISION_DAY = "day"
PRECISION_MONTH = "month"

#: URL schemes a post may link to.
WEB_URL_SCHEMES = ("http", "https")

#: The JSON Schema generated from FeedDocument | FeedPostMessage.
SCHEMA_PATH = Path(__file__).with_name("sci_bots_feed.schema.json")

#: Keys an author may add without a note: editor hints and comments.
QUIET_KEY_PREFIXES = ("$", "_")

#: Characters of the url+title digest used as a derived post id.
DERIVED_ID_LENGTH = 12

#: The payload models build their validators on first use, not on import,
#: as notifications.consts does. Unknown keys are dropped (and noted).
_FEED_MODEL_CONFIG = ConfigDict(
    defer_build=True, extra="ignore", str_strip_whitespace=True
)

#: A date written "2026-11-21", or "2026-09" when only the month is known.
FeedDate = Annotated[
    datetime.date,
    WithJsonSchema(
        {
            "type": "string",
            "pattern": r"^\d{4}-\d{2}(-\d{2})?$",
            "description": 'An ISO day ("2026-11-21") or month ("2026-09").',
        }
    ),
]


def is_web_url(url):
    """Whether ``url`` is an http or https URL with a host."""
    parsed = urlparse(url)

    return parsed.scheme.lower() in WEB_URL_SCHEMES and bool(parsed.netloc)


def derive_post_id(url, title):
    """A stable id for a post that has none, from its url and title."""
    digest = hashlib.sha1(f"{url}\n{title}".encode()).hexdigest()

    return digest[:DERIVED_ID_LENGTH]


class FeedPostMessage(BaseModel):
    """One feed post, as pushed or as written in a feed file."""

    # Each field's description is its documentation, and the help an editor
    # shows from the generated JSON Schema.
    model_config = _FEED_MODEL_CONFIG

    id: str = Field(
        "",
        description="Stable id: a later post with the same id replaces this "
        "one. Derived from url and title when absent.",
    )
    title: str = Field(min_length=1, description="One line, the card's heading.")
    kind: Literal[FEED_KINDS] = Field(description="What the post is.")
    date: FeedDate
    date_precision: Literal[PRECISION_DAY, PRECISION_MONTH] = Field(
        PRECISION_DAY,
        description='Set to "month" by a "2026-09" date: the card shows '
        '"September 2026".',
    )
    summary: str = Field(
        "",
        description="Plain text; shown when there is no summary_html, and as "
        "its tooltip.",
    )
    summary_html: str = Field(
        "",
        description="Short rich text: <b>, <i>, <u>, <a href>, <ul>/<ol>/<li>, "
        "<p>, <br>. Anything else, images included, is removed before display.",
    )
    url: str = Field(
        description="Where Read more goes: an http or https page, opened in "
        "the browser.",
        json_schema_extra={"format": "uri", "pattern": "^https?://"},
    )
    image: str = Field(
        "",
        description="Optional picture: a path relative to the feed file, or "
        "an https URL. A wide picture shows as a banner.",
    )
    pinned: bool = Field(
        False, description="Pinned posts come first, whatever their date."
    )
    source: str = Field(
        "", description='Where it came from, e.g. "LinkedIn" or "Newsletter".'
    )
    expires: datetime.date | None = Field(
        None, description="Hidden after this day (ISO date)."
    )

    @model_validator(mode="before")
    @classmethod
    def _read_month_dates_and_note_unknown_keys(cls, data):
        if not isinstance(data, dict):
            return data

        unknown = [
            key
            for key in data
            if key not in cls.model_fields and not key.startswith(QUIET_KEY_PREFIXES)
        ]

        if unknown:
            logger.info(f"Feed post {data.get('title')!r}: ignored keys {unknown}")

        text = data.get("date")

        if isinstance(text, str) and len(text.strip()) == len("2026-09"):
            data = {
                **data,
                "date": f"{text.strip()}-01",
                "date_precision": PRECISION_MONTH,
            }

        return data

    @field_validator("url")
    @classmethod
    def _check_url(cls, url):
        if not is_web_url(url):
            raise ValueError("must be a web address starting with https://")

        return url

    @field_validator("image")
    @classmethod
    def _check_image(cls, image):
        scheme = urlparse(image).scheme.lower()

        # One letter is a Windows drive, not a scheme.
        if len(scheme) > 1 and scheme != "https":
            raise ValueError(
                "must be a file next to the feed or a web address starting "
                "with https://"
            )

        return image

    @model_validator(mode="after")
    def _derive_id(self):
        if not self.id:
            self.id = derive_post_id(self.url, self.title)

        return self


class FeedDocument(BaseModel):
    """A whole feed: what a feed file holds, or a batch of pushed posts."""

    model_config = ConfigDict(defer_build=True, extra="ignore", populate_by_name=True)

    schema_url: str = Field(
        "", alias="$schema", description="The JSON Schema editors check against."
    )
    readme: str = Field(
        "", alias="_readme", description="A note to the file's authors; not shown."
    )
    version: Literal[FEED_SCHEMA_VERSION] = Field(
        FEED_SCHEMA_VERSION, description="The feed file format."
    )
    posts: list[FeedPostMessage] = Field([], description="The posts, any order.")


class ParsedFeed(NamedTuple):
    """The posts a payload held, and one readable line per bad one."""

    posts: list
    errors: list


def _friendly_message(problem):
    """A pydantic problem in words an author knows."""
    kind = problem["type"]

    if kind == "missing":
        return "is required"

    if kind == "string_too_short":
        return "must not be empty"

    if kind.startswith("date"):
        return 'must be a date like "2026-11-21", or a month like "2026-09"'

    if kind == "literal_error":
        return f"must be one of {problem['ctx']['expected']}"

    return problem["msg"].removeprefix("Value error, ")


def validation_problems(error):
    """``(field, message)`` per problem in a pydantic ValidationError, the
    message in words an author knows; field is "" for the whole post."""
    return [
        (".".join(str(part) for part in problem["loc"]), _friendly_message(problem))
        for problem in error.errors()
    ]


def _error_lines(error, label):
    """One line per problem: ``label: field: message``."""
    lines = []

    for field, message in validation_problems(error):
        where = f"{label}: {field}" if field else label

        lines.append(f"{where}: {message}")

    return lines


def _post_label(index, entry):
    """How an error names a post: its number, and its id or title if any."""
    label = f"Post {index}"

    if isinstance(entry, dict):
        name = entry.get("id") or entry.get("title")

        if name:
            label = f"{label} ({str(name)[:60]!r})"

    return label


def _parse_posts(entries):
    posts, errors = [], []

    for index, entry in enumerate(entries, start=1):
        try:
            posts.append(FeedPostMessage.model_validate(entry))

        except ValidationError as error:
            errors.extend(_error_lines(error, _post_label(index, entry)))

    return ParsedFeed(posts, errors)


def parse_feed_payload(payload):
    """The valid posts in ``payload`` and a line per problem; never raises.

    ``payload`` is a FeedPostMessage, a FeedDocument, or their JSON (a str)
    or dict form; a list is taken as a list of posts.
    """

    if isinstance(payload, FeedPostMessage):
        return ParsedFeed([payload], [])

    if isinstance(payload, FeedDocument):
        return ParsedFeed(list(payload.posts), [])

    if isinstance(payload, (str, bytes)):
        try:
            payload = json.loads(payload)

        except json.JSONDecodeError as error:
            return ParsedFeed([], [f"Not valid JSON: line {error.lineno}: {error.msg}"])

    if isinstance(payload, list):
        return _parse_posts(payload)

    if not isinstance(payload, dict):
        return ParsedFeed([], ["Expected a post or a feed document (a JSON object)"])

    if "posts" not in payload:
        return _parse_posts([payload])

    if not isinstance(payload["posts"], list):
        return ParsedFeed([], ["Feed document: posts: must be a list"])

    try:
        FeedDocument.model_validate({**payload, "posts": []})

    except ValidationError as error:
        return ParsedFeed([], _error_lines(error, "Feed document"))

    return _parse_posts(payload["posts"])


def feed_json_schema():
    """The JSON Schema of a feed file or a single post."""
    adapter = TypeAdapter(FeedDocument | FeedPostMessage)
    schema = adapter.json_schema(by_alias=True)

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Sci-Bots Feed",
        "description": "A feed document, or a single post to push.",
        **schema,
    }


def write_feed_json_schema(path=SCHEMA_PATH):
    """Write the JSON Schema to ``path`` (the feed file's sibling)."""
    text = json.dumps(feed_json_schema(), indent=2, ensure_ascii=False)
    Path(path).write_text(f"{text}\n", encoding="utf-8")

    return path


if __name__ == "__main__":
    print(f"Wrote {write_feed_json_schema()}")
