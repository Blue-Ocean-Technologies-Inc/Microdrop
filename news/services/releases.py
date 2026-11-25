# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Recent MicroDrop releases as feed posts, read from the local CHANGELOG.md.

Qt-free. commitizen writes the changelog as::

    ## [v1.46.0](https://…/releases/tag/v1.46.0) (2026-11-18)

    ### Feat

    - **image_viewer**: ROI tree with a section per experiment ([`5a4ae80`](…))

The feed shows the RELEASE_POST_COUNT most recent releases with at least
one feature (filled with the most recent others if too few have any). A
post's summary lists that release's own feature lines, or its fixes when
it has none, cleaned of markdown and commit links: nothing is reworded.
Generated on every load, never written to the feed file.
"""

# Standard library imports.
import datetime
import re
from html import escape
from pathlib import Path
from typing import NamedTuple

# Enthought library imports.
from traits.api import File, HasTraits, provides

# Microdrop package imports.
from microdrop_application.consts import CHANGELOG_PATH

# Local imports.
from .feed_html import html_to_plain_text, sanitise_summary_html
from .feed_sources import FeedLoadError, IFeedSource

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The changelog of the checkout the demo runs in.
DEFAULT_CHANGELOG_PATH = CHANGELOG_PATH

#: Releases shown in the feed.
RELEASE_POST_COUNT = 3

#: Whether releases without a feature give way to older ones that have one.
RELEASES_NEED_FEATURES = True

#: Lines listed in a release's summary before "and N more".
RELEASE_SUMMARY_MAX_ENTRIES = 5

#: The changelog sections listed: features, else fixes.
FEATURE_SECTION = "Feat"
FIX_SECTION = "Fix"

#: How the list is introduced, per section.
SECTION_INTROS = {FEATURE_SECTION: "New:", FIX_SECTION: "Fixes:"}

RELEASE_URL = (
    "https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/releases/tag/v{version}"
)
RELEASE_SOURCE_LABEL = "Release notes"

#: "## [v1.46.0](link) (2026-11-18)", the link optional.
_RELEASE_HEADING = re.compile(
    r"^## \[?v?(?P<version>\d+\.\d+\.\d+[\w.+-]*)\]?(?:\([^)]*\))?\s+"
    r"\((?P<date>\d{4}-\d{2}-\d{2})\)\s*$"
)
_SECTION_HEADING = re.compile(r"^### (?P<name>.+?)\s*$")
_BULLET = re.compile(r"^[-*] (?P<text>.+)$")

#: A trailing "([`5a4ae80`](https://…/commit/…))".
_COMMIT_LINK = re.compile(r"\s*\(\[`?[0-9a-f]{7,40}`?\]\([^)]*\)\)\s*$")
_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_EMPHASIS = re.compile(r"(\*\*|__|`)(.+?)\1")


class Release(NamedTuple):
    """One release: its version, date and changelog lines per section."""

    version: str
    date: datetime.date
    sections: dict


def clean_entry(text):
    """A changelog bullet as plain text: no commit link, markdown links
    reduced to their text, no bold or code marks."""
    text = _COMMIT_LINK.sub("", text)
    text = _MARKDOWN_LINK.sub(r"\1", text)

    return _EMPHASIS.sub(r"\2", text).strip()


def parse_changelog(text):
    """The releases in a commitizen changelog, as they appear. A "## "
    heading that is not a release is logged and its lines skipped."""
    releases = []
    release = None
    section = None

    for line in text.splitlines():
        if line.startswith("## "):
            match = _RELEASE_HEADING.match(line)
            release = section = None

            if match is None:
                logger.info(f"Changelog heading skipped, not a release: {line!r}")

                continue

            try:
                day = datetime.date.fromisoformat(match["date"])

            except ValueError:
                logger.info(f"Changelog heading skipped, bad date: {line!r}")

                continue

            release = Release(match["version"], day, {})
            releases.append(release)

            continue

        if release is None:
            continue

        heading = _SECTION_HEADING.match(line)

        if heading is not None:
            section = heading["name"]
            release.sections.setdefault(section, [])

            continue

        bullet = _BULLET.match(line)

        if bullet is not None and section is not None:
            entry = clean_entry(bullet["text"])

            if entry:
                release.sections[section].append(entry)

    return releases


def select_releases(
    releases, count=RELEASE_POST_COUNT, need_features=RELEASES_NEED_FEATURES
):
    """The ``count`` most recent releases, newest first; with
    ``need_features``, those with a feature line come before any without."""
    newest_first = sorted(releases, key=lambda release: release.date, reverse=True)

    if not need_features:
        return newest_first[:count]

    picked = [
        release for release in newest_first if release.sections.get(FEATURE_SECTION)
    ]
    picked = picked[:count]

    for release in newest_first:
        if len(picked) >= count:
            break

        if release not in picked:
            picked.append(release)

    return sorted(picked, key=lambda release: release.date, reverse=True)


def release_summary_html(release):
    """The release's feature lines (else its fixes) as a short list,
    sanitised; "" if it has neither."""

    for section in (FEATURE_SECTION, FIX_SECTION):
        entries = release.sections.get(section)

        if entries:
            break

    else:
        return ""

    shown = entries[:RELEASE_SUMMARY_MAX_ENTRIES]
    items = "".join(f"<li>{escape(entry)}</li>" for entry in shown)
    more = len(entries) - len(shown)
    html = f"<p>{SECTION_INTROS[section]}</p><ul>{items}</ul>"

    if more:
        html = f"{html}<p>and {more} more</p>"

    return sanitise_summary_html(html)


def release_post(release):
    """The feed post data for ``release``."""
    summary_html = release_summary_html(release)

    return {
        "id": f"release-v{release.version}",
        "title": f"MicroDrop v{release.version}",
        "kind": "release",
        "date": release.date.isoformat(),
        "source": RELEASE_SOURCE_LABEL,
        "summary": html_to_plain_text(summary_html),
        "summary_html": summary_html,
        "url": RELEASE_URL.format(version=release.version),
    }


@provides(IFeedSource)
class ChangelogFeedSource(HasTraits):
    """The most recent releases in a local CHANGELOG.md, as posts."""

    #: The changelog; never written.
    path = File(str(DEFAULT_CHANGELOG_PATH))

    def load(self):
        path = Path(self.path)

        try:
            text = path.read_text(encoding="utf-8")

        except (OSError, ValueError) as error:
            raise FeedLoadError(f"Could not read {path.name}: {error}") from None

        releases = parse_changelog(text)

        if not releases:
            raise FeedLoadError(f"No releases found in {path.name}")

        return [release_post(release) for release in select_releases(releases)]

    def resolve_image(self, image):
        return image
