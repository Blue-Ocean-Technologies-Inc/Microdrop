# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Sci-Bots Feed controller: source posts merged with pushed ones by
id, pushes surviving reloads, expired posts hidden, problems reported
without dropping good posts, and only web links opened."""

# Standard library imports.
import datetime
import json

# Third-party imports.
import pytest

# Microdrop package imports.
from news.controllers.feed_controller import (
    SciBotsFeedController,
)
from news.models.feed_model import (
    ORIGIN_PUSHED,
    ORIGIN_SOURCE,
    SciBotsFeed,
)
from news.services.feed_sources import (
    JsonFileFeedSource,
    feed_file_sources,
)

#: The injected clock.
TODAY = datetime.date(2026, 11, 23)

URL = "https://www.linkedin.com/company/sci-bots-inc./posts/"


def _post(post_id, date="2026-11-20", **fields):
    return {
        "id": post_id,
        "title": f"Post {post_id}",
        "date": date,
        "kind": "post",
        "url": URL,
        **fields,
    }


def _controller(tmp_path, posts):
    path = tmp_path / "feed.json"
    path.write_text(json.dumps({"version": 1, "posts": posts}), encoding="utf-8")

    controller = SciBotsFeedController(
        model=SciBotsFeed(today=lambda: TODAY),
        sources=[JsonFileFeedSource(path=str(path))],
    )
    controller.reload()

    return controller, path


def _ids(controller):
    return [post.id for post in controller.model.posts]


def test_reload_shows_pinned_then_newest(tmp_path):
    controller, _path = _controller(
        tmp_path,
        [
            _post("old", "2026-10-01"),
            _post("pinned", "2026-01", pinned=True),
            _post("new", "2026-11-21"),
        ],
    )

    assert _ids(controller) == ["pinned", "new", "old"]
    assert controller.model.summary == "3 posts · newest 2 days ago"
    # A clean load says nothing: the feed itself shows it.
    assert controller.model.status_text == ""
    assert not controller.model.status_is_error


def test_push_adds_and_updates_by_id(tmp_path):
    controller, _path = _controller(tmp_path, [_post("a")])

    result = controller.push([_post("a", title="A, edited"), _post("b", "2026-11-22")])

    assert (result.added, result.updated, result.errors) == (["b"], ["a"], [])
    assert _ids(controller) == ["b", "a"]
    assert controller.model.posts[1].title == "A, edited"
    assert controller.model.posts[1].origin == ORIGIN_PUSHED


def test_pushed_posts_survive_a_reload_and_supersede_the_file(tmp_path):
    controller, path = _controller(tmp_path, [_post("a"), _post("b")])
    controller.push(_post("a", title="pushed"))

    path.write_text(
        json.dumps({"posts": [_post("a", title="file"), _post("c")]}), encoding="utf-8"
    )
    controller.reload()

    titles = {post.id: (post.title, post.origin) for post in controller.model.posts}

    assert titles == {
        "a": ("pushed", ORIGIN_PUSHED),
        "c": ("Post c", ORIGIN_SOURCE),
    }


def test_a_bad_post_is_reported_and_the_good_ones_kept(tmp_path):
    controller, _path = _controller(tmp_path, [])

    result = controller.push(
        {"posts": [_post("good"), _post("bad", kind="rumour", url="ftp://x")]}
    )

    assert result.added == ["good"]
    assert len(result.errors) == 2
    assert _ids(controller) == ["good"]
    assert controller.model.status_is_error
    assert controller.model.status_text.splitlines()[0] == (
        "Pushed 1 new post, 0 updates; 2 problems:"
    )


def test_invalid_json_pushes_nothing(tmp_path):
    controller, _path = _controller(tmp_path, [_post("a")])

    result = controller.push("{not json")

    assert result.errors[0].startswith("Not valid JSON")
    assert _ids(controller) == ["a"]
    assert controller.model.status_text.startswith("Nothing pushed; 1 problem:")


def test_expired_posts_are_hidden(tmp_path):
    controller, _path = _controller(
        tmp_path, [_post("gone", expires="2026-11-22"), _post("kept")]
    )

    assert _ids(controller) == ["kept"]
    assert controller.model.status_text == ""


def test_remove_hides_until_pushed_again(tmp_path):
    controller, _path = _controller(tmp_path, [_post("a"), _post("b")])

    controller.remove("a")
    controller.reload()

    assert _ids(controller) == ["b"]

    controller.push(_post("a"))

    assert sorted(_ids(controller)) == ["a", "b"]


def test_a_missing_file_keeps_pushed_posts(tmp_path):
    controller, path = _controller(tmp_path, [_post("a")])
    controller.push(_post("p"))

    path.unlink()
    controller.reload()

    assert _ids(controller) == ["p"]
    assert controller.model.status_text.splitlines()[1].startswith(
        "Feed source unavailable: No feed file"
    )
    assert controller.model.status_is_error


def test_rich_summaries_are_sanitised(tmp_path):
    controller, _path = _controller(
        tmp_path, [_post("a", summary_html="<b>hi</b><script>x()</script>")]
    )

    assert controller.model.posts[0].summary_html == "<b>hi</b>"


def test_push_file_resolves_images_next_to_it(tmp_path):
    controller, _path = _controller(tmp_path, [])
    pushed = tmp_path / "sub" / "post.json"
    pushed.parent.mkdir()
    pushed.write_text(json.dumps(_post("p", image="pic.png")), encoding="utf-8")

    controller.push_file(pushed)

    assert controller.model.posts[0].image == str((pushed.parent / "pic.png").resolve())


def test_pictures_resolve_next_to_their_feed_file(tmp_path):
    images = [{"src": "a.png", "caption": "A"}, {"src": "https://x.com/b.png"}]
    controller, path = _controller(tmp_path, [_post("p", images=images)])
    post = controller.model.posts[0]

    assert post.images == [
        (str((path.parent / "a.png").resolve()), "A", ""),
        ("https://x.com/b.png", "", ""),
    ]
    assert post.image == post.images[0][0]


def test_local_posts_join_the_demo_feed_only_when_present(tmp_path):
    feed, local = tmp_path / "feed.json", tmp_path / "local" / "posts.json"

    assert [source.path for source in feed_file_sources(feed, local)] == [str(feed)]

    local.parent.mkdir()
    local.write_text("{}", encoding="utf-8")

    paths = [source.path for source in feed_file_sources(feed, local)]

    assert paths == [str(local), str(feed)]


@pytest.mark.parametrize(
    "url, opened",
    [
        (URL, True),
        ("http://example.com/news", True),
        ("file:///C:/Windows/notepad.exe", False),
        ("javascript:alert(1)", False),
        ("#read-more", False),
        ("", False),
    ],
)
def test_only_web_links_are_opened(url, opened):
    calls = []
    controller = SciBotsFeedController(open_url=calls.append)

    assert controller.open_link(url) is opened
    assert calls == ([url] if opened else [])


def test_a_failing_source_leaves_the_others_and_ids_dedupe(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps([_post("a", title="first")]), encoding="utf-8")
    second.write_text(
        json.dumps([_post("a", title="second"), _post("b")]), encoding="utf-8"
    )
    controller = SciBotsFeedController(
        model=SciBotsFeed(today=lambda: TODAY),
        sources=[
            JsonFileFeedSource(path=str(tmp_path / "missing.json")),
            JsonFileFeedSource(path=str(first)),
            JsonFileFeedSource(path=str(second)),
        ],
    )

    controller.reload()

    titles = {post.id: post.title for post in controller.model.posts}

    assert titles == {"a": "first", "b": "Post b"}
    assert controller.model.status_text.startswith("Loaded 2 posts; 1 problem:")


def test_posts_are_grouped_under_their_headers(tmp_path):
    controller, _path = _controller(
        tmp_path,
        [
            _post("n1", "2026-09", kind="newsletter"),
            _post("pin", "2026-01-01", kind="newsletter", pinned=True),
            _post("p1", "2026-11-20"),
            _post("a1", "2026-11-21", kind="product"),
        ],
    )
    groups = [
        (group.spec.id, [post.id for post in group.posts])
        for group in controller.model.groups
    ]

    assert groups == [
        ("pinned", ["pin"]),
        ("newsletters", ["n1"]),
        ("announcements", ["a1"]),
        ("posts", ["p1"]),
    ]


def test_show_all_survives_a_reload(tmp_path):
    posts = [_post(f"p{day}", f"2026-11-{day:02d}") for day in range(1, 6)]
    controller, _path = _controller(tmp_path, posts)
    group = controller.model.groups[0]

    assert (len(group.visible_posts), group.hidden_count) == (3, 2)

    controller.toggle_show_all(group)
    controller.reload()

    group = controller.model.groups[0]

    assert group.show_all
    assert (len(group.visible_posts), group.hidden_count) == (5, 0)


def test_dismissing_clears_the_status(tmp_path):
    controller, _path = _controller(tmp_path, [])
    controller.push("{not json")

    controller.dismiss_status()

    assert (controller.model.status_text, controller.model.status_is_error) == (
        "",
        False,
    )
