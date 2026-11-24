# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The feed creator: byte-stable saves, dirty tracking, checks worded for
authors, partial loads, a rich-text box that pastes clean, and atomic
writes. No window is shown: the controller runs against its model."""

# Standard library imports.
import datetime
import json
import os

# Qt reads the platform when the first QApplication is made; set it first.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets

# Microdrop package imports.
from examples.demos.notifications_pane import feed_creator_controller
from examples.demos.notifications_pane.feed_creator_controller import (
    FeedCreatorController,
)
from examples.demos.notifications_pane.feed_creator_io import write_atomically
from examples.demos.notifications_pane.feed_creator_model import (
    CHECK_ERROR,
    CHECK_WARNING,
    EditablePost,
)
from examples.demos.notifications_pane.feed_creator_rich_text import (
    _CleanPasteTextEdit,
    document_to_summary_html,
)
from examples.demos.notifications_pane.sci_bots_feed_sources import (
    DEFAULT_FEED_PATH,
)

URL = "https://www.linkedin.com/company/sci-bots-inc./posts/"


@pytest.fixture
def dialogs(monkeypatch):
    """Answer every dialog Yes and record what they said."""
    said = []

    def answer(parent=None, message="", **kwargs):
        said.append(message)

        return feed_creator_controller.YES

    monkeypatch.setattr(feed_creator_controller, "confirm", answer)
    monkeypatch.setattr(feed_creator_controller, "warning", answer)

    return said


def _opened(path):
    controller = FeedCreatorController()
    controller.open_file(path)

    return controller


def _post(**fields):
    values = {
        "title": "A post",
        "kind": "post",
        "date": datetime.date(2026, 11, 20),
        "summary": "Some words.",
        "url": URL,
    }

    return EditablePost(**(values | fields))


def test_open_then_save_is_byte_stable(tmp_path, dialogs):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    controller = _opened(DEFAULT_FEED_PATH)

    assert controller._write(first)

    assert _opened(first)._write(second)
    assert first.read_bytes() == second.read_bytes()


def test_saved_files_are_pretty_utf8_with_schema_version_and_ids(tmp_path, dialogs):
    path = tmp_path / "feed.json"
    controller = FeedCreatorController()
    controller.model.posts = [
        _post(title="Café — news", date=datetime.date(2026, 9, 1))
    ]
    controller.model.posts[0].month_only = True

    assert controller._write(path)

    text = path.read_text(encoding="utf-8")
    data = json.loads(text)

    assert "Café — news" in text
    assert text.startswith('{\n  "$schema": ')
    assert data["version"] == 1
    assert list(data["posts"][0]) == ["id", "title", "kind", "date", "summary", "url"]
    assert data["posts"][0]["date"] == "2026-09"


def test_edits_mark_dirty_and_saving_clears_it(tmp_path, dialogs):
    controller = _opened(DEFAULT_FEED_PATH)

    assert not controller.model.dirty

    controller.model.posts[0].title = "Changed"

    assert controller.model.dirty
    assert controller.model.title.startswith("*")
    assert controller._write(tmp_path / "saved.json")
    assert not controller.model.dirty


def test_adding_and_deleting_mark_dirty(dialogs):
    controller = _opened(DEFAULT_FEED_PATH)

    controller._add_clicked(None)

    assert controller.model.dirty
    assert controller.model.selected in controller.model.posts


@pytest.mark.parametrize(
    "fields, severity, expected",
    [
        ({"url": "www.sci-bots.com"}, CHECK_ERROR, "the link must be a web address"),
        ({"url": ""}, CHECK_ERROR, "the link is required"),
        ({"title": ""}, CHECK_ERROR, "the title is required"),
        ({"image": "C:/pictures/x.png"}, CHECK_WARNING, "the picture is a file"),
        ({"summary": ""}, CHECK_WARNING, "the summary is empty"),
        ({"url": "http://sci-bots.com"}, CHECK_WARNING, "the link is not secure"),
    ],
)
def test_checks_are_worded_for_authors(fields, severity, expected):
    controller = FeedCreatorController()
    controller.model.posts = [_post(**({"title": "MicroTAS 2026 and DMF"} | fields))]

    controller.check()

    texts = [
        check.text for check in controller.model.checks if check.severity == severity
    ]

    assert any(text.startswith("Post 1 '") and expected in text for text in texts), (
        texts
    )
    assert controller.model.has_errors == (severity == CHECK_ERROR)


def test_an_error_marks_its_field_and_blocks_saving(tmp_path, dialogs):
    controller = FeedCreatorController()
    controller.model.posts = [_post(url="javascript:alert(1)")]

    assert not controller._write(tmp_path / "x.json")
    assert controller.model.posts[0].url_invalid
    assert not (tmp_path / "x.json").exists()
    assert "Fix the errors" in dialogs[-1]


def test_a_file_with_a_bad_post_opens_its_good_ones(tmp_path, dialogs):
    path = tmp_path / "feed.json"
    good = {"title": "Good", "date": "2026-11-20", "kind": "post", "url": URL}
    path.write_text(
        json.dumps({"posts": [good, {"title": "Bad", "kind": "rumour"}]}),
        encoding="utf-8",
    )

    controller = _opened(path)

    assert [post.title for post in controller.model.posts] == ["Good"]
    assert any(
        check.text.startswith("Could not be read") and "Post 2 ('Bad')" in check.text
        for check in controller.model.checks
    )
    assert not controller.model.has_errors


def test_writes_are_atomic(tmp_path, monkeypatch):
    path = tmp_path / "feed.json"
    path.write_text("old", encoding="utf-8")

    def fail(source, target):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail)

    with pytest.raises(OSError):
        write_atomically(path, "new")

    assert path.read_text(encoding="utf-8") == "old"
    assert [item.name for item in tmp_path.iterdir()] == ["feed.json"]


def test_pasted_styled_html_comes_out_clean():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    editor = _CleanPasteTextEdit()
    mime = QtCore.QMimeData()
    mime.setHtml(
        '<p class="MsoNormal" style="font-family:Calibri;color:#ff0000;'
        'font-size:20pt"><span style="font-weight:bold"><b>Bold</b></span> and '
        '<i>italic</i> <a href="https://sci-bots.com" onclick="x()">site</a>'
        '<img src="https://x.com/p.png"><script>alert(1)</script></p>'
        "<ul><li>one</li><li>two</li></ul>"
    )

    editor.insertFromMimeData(mime)
    html = document_to_summary_html(editor.document())

    assert app is not None
    assert html == (
        '<p><b>Bold</b> and <i>italic</i> <a href="https://sci-bots.com">site</a>'
        "</p><ul><li>one</li><li>two</li></ul>"
    )
