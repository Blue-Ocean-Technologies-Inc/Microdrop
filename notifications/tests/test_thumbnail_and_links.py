# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A message's thumbnail and detail links: optional, local paths only,
carried onto the entry and kept by a thread's update; a link opens a
folder, never a file."""

# Third-party imports.
import pytest
from pydantic import ValidationError

# Microdrop package imports.
from notifications.consts import DetailLink, NotificationMessage
from notifications.models.notification import link_folder
from notifications.models.notification_center import NotificationCenter


def test_a_message_without_them_is_unchanged():
    message = NotificationMessage.model_validate({"title": "t"})

    assert message.thumbnail == ""
    assert message.links == []


def test_local_paths_are_accepted():
    message = NotificationMessage.model_validate(
        {
            "title": "Photo captured",
            "detail": "a.png",
            "thumbnail": r"C:\captures\a.png",
            "links": [{"text": "a.png", "path": "/home/me/captures/a.png"}],
        }
    )

    assert message.thumbnail == r"C:\captures\a.png"
    assert message.links == [DetailLink(text="a.png", path="/home/me/captures/a.png")]


@pytest.mark.parametrize(
    "thumbnail", ["https://example.com/a.png", "data:image/png;base64,AAAA"]
)
def test_a_url_or_data_is_no_thumbnail(thumbnail):

    with pytest.raises(ValidationError):
        NotificationMessage.model_validate({"title": "t", "thumbnail": thumbnail})


@pytest.mark.parametrize(
    "link",
    [
        {"text": "a", "path": "https://example.com"},
        {"text": "", "path": "/a"},
        {"text": "a", "path": ""},
    ],
)
def test_a_link_needs_text_and_a_local_path(link):

    with pytest.raises(ValidationError):
        NotificationMessage.model_validate({"title": "t", "links": [link]})


def test_the_entry_carries_them_and_a_thread_update_replaces_them():
    center = NotificationCenter()
    first = NotificationMessage.model_validate(
        {
            "title": "Photo captured",
            "thread_id": "photos",
            "thumbnail": "/c/a.png",
            "links": [{"text": "a.png", "path": "/c/a.png"}],
        }
    )
    second = first.model_copy(
        update={"thumbnail": "/c/b.png", "links": [DetailLink(text="b", path="/c")]}
    )

    entry = center.post_message(first)

    assert entry.thumbnail == "/c/a.png"
    assert [link.text for link in entry.links] == ["a.png"]

    center.post_message(second)

    assert entry.thumbnail == "/c/b.png"
    assert [link.path for link in entry.links] == ["/c"]


def test_a_link_opens_a_folder_never_a_file(tmp_path):
    photo = tmp_path / "a.png"
    photo.write_bytes(b"")

    assert link_folder(tmp_path) == tmp_path
    assert link_folder(photo) == tmp_path
    assert link_folder(tmp_path / "gone.png") == tmp_path
