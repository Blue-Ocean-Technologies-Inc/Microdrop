# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Where the Sci-Bots Feed's own posts come from. Qt-free.

A source's ``load()`` returns the raw feed payload; the controller
validates it the same way as a pushed one. The only source is a
hand-edited JSON file; a network source would be another IFeedSource.
"""

# Standard library imports.
import json
from pathlib import Path

# Enthought library imports.
from traits.api import File, HasTraits, Interface, provides

# Local imports.
from ..consts import FEED_PATH, LOCAL_POSTS_PATH


class FeedLoadError(Exception):
    """A feed source could not be read; the message is the one-line reason."""


class IFeedSource(Interface):
    """Where the feed's own posts come from."""

    def load(self):
        """The feed payload (a FeedDocument as a dict, or a list of posts);
        raises FeedLoadError, with a one-line reason, if there is none."""

    def resolve_image(self, image):
        """A post's ``image`` made absolute against the source, if it is a
        relative path; URLs and absolute paths come back unchanged."""


@provides(IFeedSource)
class JsonFileFeedSource(HasTraits):
    """A hand-edited JSON feed file, re-read on every load."""

    #: The feed file.
    path = File()

    def load(self):
        path = Path(self.path)

        try:
            return json.loads(path.read_text(encoding="utf-8"))

        except FileNotFoundError:
            raise FeedLoadError(f"No feed file at {path}") from None

        except json.JSONDecodeError as error:
            raise FeedLoadError(
                f"{path.name} is not valid JSON (line {error.lineno}: {error.msg})"
            ) from None

        except (OSError, ValueError) as error:
            raise FeedLoadError(f"Could not read {path.name}: {error}") from None

    def resolve_image(self, image):
        return resolve_image_path(image, Path(self.path).parent)


def resolve_image_path(image, base_dir):
    """``image`` against ``base_dir`` if it is a relative path, else as is."""

    if not image or "://" in image or Path(image).is_absolute():
        return image

    return str((Path(base_dir) / image).resolve())


def feed_file_sources(path=FEED_PATH, local_path=LOCAL_POSTS_PATH):
    """The feed's file sources: the local-only posts first, when that
    file exists (so they win on a shared id), then the feed file."""
    sources = [JsonFileFeedSource(path=str(path))]

    if Path(local_path).is_file():
        sources.insert(0, JsonFileFeedSource(path=str(local_path)))

    return sources
