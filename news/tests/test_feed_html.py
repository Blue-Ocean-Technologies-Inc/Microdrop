# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A feed post's summary_html is cut down to a safe allow-list before Qt
shows it: no scripts, handlers, styles, images or non-web links, and
always well formed."""

# Third-party imports.
import pytest

# Microdrop package imports.
from news.services.feed_html import (
    html_to_plain_text,
    sanitise_summary_html,
)


@pytest.mark.parametrize(
    "html, expected",
    [
        ("<b>bold</b> and <i>it</i>", "<b>bold</b> and <i>it</i>"),
        ("a<script>alert(1)</script>b", "ab"),
        ("<style>p {color: red}</style>text", "text"),
        ("<iframe src='https://x.com'>inside</iframe>after", "after"),
        (
            '<a href="javascript:alert(1)">click</a>',
            "<a>click</a>",
        ),
        (
            '<a href="https://sci-bots.com" onclick="x()" target="_blank">ok</a>',
            '<a href="https://sci-bots.com">ok</a>',
        ),
        ('<b onclick="steal()" style="color:red">b</b>', "<b>b</b>"),
        ('<img src="https://x.com/t.png" onerror="x()">pic', "pic"),
        ('<p>one<img src="x.png"/>two</p>', "<p>onetwo</p>"),
        (
            "<ul><li>a<ol><li>b</li></ol></li></ul>",
            "<ul><li>a<ol><li>b</li></ol></li></ul>",
        ),
        ("<b>open <i>both", "<b>open <i>both</i></b>"),
        ("<b>x</i></b>", "<b>x</b>"),
        ("<p>a<b>b</p>c", "<p>a<b>b</b></p>c"),
        ("<div><span>kept text</span></div>", "kept text"),
        ("line<br>break", "line<br>break"),
        ("1 &lt; 2 &amp; <3", "1 &lt; 2 &amp; &lt;3"),
        ("<script>never closed <b>x</b>", ""),
    ],
)
def test_summary_html_is_sanitised(html, expected):
    assert sanitise_summary_html(html) == expected


def test_a_link_href_is_escaped():
    html = sanitise_summary_html('<a href="https://x.com/?a=1&b=&quot;2">l</a>')

    assert html == '<a href="https://x.com/?a=1&amp;b=&quot;2">l</a>'


def test_plain_text_keeps_a_line_per_block_and_bullets():
    html = "<p><b>Hi</b> there</p><ul><li>one</li><li>two</li></ul><script>x</script>"

    assert html_to_plain_text(html) == "Hi there\n• one\n• two"
