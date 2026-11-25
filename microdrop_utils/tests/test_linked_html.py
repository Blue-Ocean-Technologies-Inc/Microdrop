# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A clamped label's links: the first occurrence of each text becomes an
anchor naming its index, and nothing else in the text becomes markup."""

# Microdrop utils imports.
from microdrop_utils.clamped_label import linked_html

LINK = '<a href="{index}" style="color: red;">{text}</a>'


def test_the_first_occurrence_of_a_link_text_is_an_anchor():
    html = linked_html(["Latest: a.png, not a.png"], ["a.png"], "red")

    assert html == "Latest: " + LINK.format(index=0, text="a.png") + ", not a.png"


def test_lines_are_joined_by_breaks_and_links_found_on_any():
    html = linked_html(["first", "b.mkv (1:05)"], ["b.mkv"], "red")

    assert html == "first<br>" + LINK.format(index=0, text="b.mkv") + " (1:05)"


def test_several_links_keep_their_indices_in_text_order():
    html = linked_html(["x then y"], ["y", "x"], "red")

    assert html == (
        LINK.format(index=1, text="x") + " then " + LINK.format(index=0, text="y")
    )


def test_markup_in_the_text_is_escaped():
    html = linked_html(["<b>&</b> <x>.png"], ["<x>.png"], "red")

    assert html == "&lt;b&gt;&amp;&lt;/b&gt; " + LINK.format(
        index=0, text="&lt;x&gt;.png"
    )


def test_a_link_text_not_shown_is_no_link():
    assert linked_html(["Latest: a.p…"], ["a.png"], "red") == "Latest: a.p…"
