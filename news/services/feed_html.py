# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Make a post's ``summary_html`` safe to show as Qt rich text. Qt-free.

An allow-list, not a block-list: only the tags in ALLOWED_TAGS survive, with
no attributes but an http or https ``href`` on a link. Scripts, styles,
frames and the like go with their contents; images go (the card's own
image is the only picture, and nothing in a summary loads a resource); any
other tag is dropped and its text kept. Text is re-escaped, stray end tags
are ignored and unclosed tags are closed, so the result is well formed.
"""

# Standard library imports.
from html import escape
from html.parser import HTMLParser

# Local imports.
from ..models.feed_schema import is_web_url

#: Tags kept, without attributes (but a link's href).
ALLOWED_TAGS = frozenset(
    {"a", "b", "br", "code", "em", "i", "li", "ol", "p", "strong", "u", "ul"}
)

#: How a list item starts in plain text.
PLAIN_TEXT_BULLET = "• "

#: Tags without an end tag.
VOID_TAGS = frozenset({"br"})

#: Tags dropped together with everything inside them.
DROPPED_WITH_CONTENTS = frozenset(
    {
        "embed",
        "head",
        "iframe",
        "math",
        "noscript",
        "object",
        "script",
        "select",
        "style",
        "svg",
        "template",
        "textarea",
        "title",
    }
)


class _Sanitiser(HTMLParser):
    """Rebuilds the allowed part of the HTML it is fed."""

    def __init__(self):
        super().__init__(convert_charrefs=True)

        self.parts = []
        self._open = []
        self._dropping = []

    def handle_starttag(self, tag, attrs):
        if self._dropping:
            if tag in DROPPED_WITH_CONTENTS:
                self._dropping.append(tag)

            return

        if tag in DROPPED_WITH_CONTENTS:
            self._dropping.append(tag)

            return

        if tag not in ALLOWED_TAGS:
            return

        if tag in VOID_TAGS:
            self.parts.append(f"<{tag}>")

            return

        self.parts.append(self._start_tag(tag, dict(attrs)))
        self._open.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag in VOID_TAGS and not self._dropping:
            self.parts.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if self._dropping:
            if tag == self._dropping[-1]:
                self._dropping.pop()

            return

        if tag not in self._open:
            return

        # Close whatever was left open inside it, then the tag itself.
        while self._open:
            open_tag = self._open.pop()
            self.parts.append(f"</{open_tag}>")

            if open_tag == tag:
                break

    def handle_data(self, data):
        if not self._dropping:
            self.parts.append(escape(data, quote=False))

    def close(self):
        super().close()

        while self._open:
            self.parts.append(f"</{self._open.pop()}>")

    @staticmethod
    def _start_tag(tag, attrs):
        href = (attrs.get("href") or "").strip()

        if tag == "a" and is_web_url(href):
            return f'<a href="{escape(href, quote=True)}">'

        return f"<{tag}>"


class _PlainText(HTMLParser):
    """Collects the readable text of sanitised HTML, a line per block."""

    def __init__(self):
        super().__init__(convert_charrefs=True)

        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "br", "li", "ul", "ol"):
            self.parts.append("\n")

        if tag == "li":
            self.parts.append(PLAIN_TEXT_BULLET)

    def handle_data(self, data):
        self.parts.append(data)


def sanitise_summary_html(html):
    """``html`` cut down to ALLOWED_TAGS, safe to show as Qt rich text."""
    sanitiser = _Sanitiser()
    sanitiser.feed(html)
    sanitiser.close()

    return "".join(sanitiser.parts).strip()


def html_to_plain_text(html):
    """The text of ``html`` (sanitised first), a line per paragraph or list
    item, list items bulleted."""
    collector = _PlainText()
    collector.feed(sanitise_summary_html(html))
    collector.close()

    lines = "".join(collector.parts).splitlines()

    return "\n".join(line.strip() for line in lines if line.strip())
