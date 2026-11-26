# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Sci-Bots Feed input contract: strict on what protects the user,
lenient for authors, one readable line per problem, and a JSON Schema
file that matches the models."""

# Standard library imports.
import datetime
import json

# Third-party imports.
import pytest

# Microdrop package imports.
from news.consts import FEED_PATH as DEFAULT_FEED_PATH
from news.consts import RESOURCES_DIR
from news.models.feed_schema import (
    PRECISION_MONTH,
    SCHEMA_PATH,
    FeedDocument,
    FeedPostMessage,
    derive_post_id,
    feed_json_schema,
    parse_feed_payload,
)

URL = "https://www.linkedin.com/company/sci-bots-inc./posts/"


def _post(**fields):
    return {"title": "A post", "date": "2026-11-20", "kind": "post", "url": URL} | (
        fields
    )


def test_a_month_date_is_its_first_day_with_month_precision():
    post = FeedPostMessage.model_validate(_post(date="2026-09"))

    assert post.date == datetime.date(2026, 9, 1)
    assert post.date_precision == PRECISION_MONTH


def test_a_missing_id_is_derived_from_url_and_title_and_stable():
    first = FeedPostMessage.model_validate(_post())
    again = FeedPostMessage.model_validate(_post(summary="changed"))

    assert first.id == again.id == derive_post_id(URL, "A post")
    assert FeedPostMessage.model_validate(_post(id="mine")).id == "mine"


def test_unknown_keys_are_ignored():
    post = FeedPostMessage.model_validate(_post(colour="red", _note="hi"))

    assert not hasattr(post, "colour")


@pytest.mark.parametrize(
    "fields, expected",
    [
        ({"kind": "rumour"}, "kind: must be one of 'announcement'"),
        ({"url": "javascript:alert(1)"}, "url: must be a web address"),
        ({"url": "file:///C:/x.html"}, "url: must be a web address"),
        ({"title": ""}, "title: must not be empty"),
        ({"date": "21 Nov"}, 'date: must be a date like "2026-11-21"'),
        ({"image": "http://x.com/a.png"}, "image: must be a file next to the feed"),
        (
            {"images": [{"src": "http://x.com/a.png"}]},
            "images.0.src: must be a file next to the feed",
        ),
        ({"images": [{"src": "a.png"}] * 3}, "images: List should have at most 2"),
    ],
)
def test_a_bad_field_is_rejected_in_one_line_naming_post_and_field(fields, expected):
    parsed = parse_feed_payload([_post(), _post(id="bad", **fields)])

    assert len(parsed.posts) == 1
    assert len(parsed.errors) == 1
    assert parsed.errors[0].startswith("Post 2 ('bad'): ")
    assert expected in parsed.errors[0]


def test_two_captioned_images_lead_and_the_first_is_the_image():
    post = FeedPostMessage.model_validate(
        _post(
            images=[
                {"src": "concept.jpg", "caption": "Concept"},
                {"src": "https://x.com/real.jpg", "caption": "The real thing"},
            ]
        )
    )

    assert [image.caption for image in post.images] == ["Concept", "The real thing"]
    assert post.image == "concept.jpg"


def test_a_single_image_reads_as_a_one_picture_list():
    post = FeedPostMessage.model_validate(_post(image="pic.png"))

    assert [(image.src, image.caption) for image in post.images] == [("pic.png", "")]


def test_a_missing_title_is_named_by_index():
    entry = _post()
    del entry["title"]

    assert parse_feed_payload([entry]).errors == ["Post 1: title: is required"]


def test_a_document_keeps_its_good_posts():
    document = {"version": 1, "posts": [_post(), {"title": "broken"}, _post(id="b")]}
    parsed = parse_feed_payload(json.dumps(document))

    assert [post.id for post in parsed.posts] == [derive_post_id(URL, "A post"), "b"]
    assert all(line.startswith("Post 2 ('broken')") for line in parsed.errors)


@pytest.mark.parametrize(
    "payload, expected",
    [
        ('{"posts": [', "Not valid JSON: line 1"),
        ({"version": 2, "posts": []}, "Feed document: version:"),
        ({"posts": "none"}, "Feed document: posts: must be a list"),
        (42, "Expected a post or a feed document"),
    ],
)
def test_a_bad_payload_gives_no_posts_and_a_reason(payload, expected):
    parsed = parse_feed_payload(payload)

    assert parsed.posts == []
    assert parsed.errors[0].startswith(expected)


def test_models_pass_through_unchanged():
    post = FeedPostMessage.model_validate(_post())
    document = FeedDocument(posts=[post])

    assert parse_feed_payload(post).posts == [post]
    assert parse_feed_payload(document).posts == [post]


def test_the_schema_file_is_up_to_date():
    written = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert written == feed_json_schema(), (
        "Regenerate it: python -m news.models.feed_schema"
    )


def test_the_shipped_files_validate():
    folder = RESOURCES_DIR / "examples"
    feed = parse_feed_payload(DEFAULT_FEED_PATH.read_text(encoding="utf-8"))
    rich = parse_feed_payload((folder / "example_post_rich.json").read_text("utf-8"))
    minimal = parse_feed_payload(
        (folder / "example_post_minimal.json").read_text("utf-8")
    )
    announcement = parse_feed_payload(
        (folder / "example_post_announcement.json").read_text("utf-8")
    )
    invalid = parse_feed_payload(
        (folder / "example_posts_invalid.json").read_text("utf-8")
    )

    assert (len(feed.posts), feed.errors) == (5, [])
    assert {post.kind for post in feed.posts} == {
        "newsletter",
        "product",
        "offer",
    }
    assert (len(announcement.posts), announcement.errors) == (1, [])
    assert (len(rich.posts), rich.errors) == (1, [])
    assert (len(minimal.posts), minimal.errors) == (1, [])
    assert len(invalid.posts) == 1
    assert len(invalid.errors) == 4
