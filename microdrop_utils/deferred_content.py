# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Content built later than the place it fills (#1064, #1085).

Qt-free: the content's place exists from the start, and the
``DeferredContent`` says whether the content is still loading, is in, or
failed to build. Code that needs the content asks ``when_built``: it runs
at once for built content, or when the content is built — or, should the
build fail, its failure callback runs instead, so no request waits forever.

The device viewer's deferred sidebar sections and the dock panes built on
first show (``microdrop_utils.lazy_dock_pane``) are both deferred content.
"""

# Standard library imports.
import traceback

# Enthought library imports.
from traits.api import Any, Callable, Enum, HasTraits, List, Property, Str

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

CONTENT_LOADING = "loading"
CONTENT_BUILT = "built"
CONTENT_FAILED = "failed"


class DeferredContent(HasTraits):
    """Content built once, later, and the requests waiting on it."""

    #: What the content is called in its loading and failure text.
    title = Str()

    #: Builds and returns the content.
    build = Callable()

    #: Where the build stands.
    state = Enum(CONTENT_LOADING, CONTENT_BUILT, CONTENT_FAILED)

    #: The built content; None until it is built.
    content = Any()

    #: Why the build failed; empty otherwise.
    error = Str()

    #: The failed build's traceback; empty otherwise.
    error_traceback = Str()

    #: What shows in place of the content: loading, or why it failed.
    status_text = Property(Str, observe="title, state, error")

    #: (on_built, on_failed) pairs waiting while the content loads.
    _waiting = List()

    def _get_status_text(self):
        if self.state == CONTENT_FAILED:
            return f"{self.title} could not be loaded: {self.error}"

        return f"Loading {self.title}…"

    def build_content(self):
        """Build the content now, unless it is built or has failed already."""

        if self.state != CONTENT_LOADING:
            return

        try:
            content = self.build()

        except Exception as error:
            logger.error(f"{self.title} could not be built: {error}", exc_info=True)

            self.error_traceback = traceback.format_exc()
            self.error = str(error) or type(error).__name__
            self.state = CONTENT_FAILED
            self._notify(failed=True)

            return

        self.content = content
        self.state = CONTENT_BUILT
        self._notify(failed=False)

    def when_built(self, on_built, on_failed=None):
        """Call ``on_built(content)`` now, or once the content is built;
        ``on_failed(error)`` instead if its build fails. Callbacks run in
        the order they were registered."""

        if self.state == CONTENT_BUILT:
            on_built(self.content)

        elif self.state == CONTENT_FAILED:
            if on_failed is not None:
                on_failed(self.error)

        else:
            self._waiting.append((on_built, on_failed))

    def _notify(self, failed):
        """Run the callbacks waiting on the build; one that raises is logged
        and does not keep the others from running."""
        waiting, self._waiting = self._waiting, []

        for on_built, on_failed in waiting:
            callback, argument = (
                (on_failed, self.error) if failed else (on_built, self.content)
            )

            if callback is None:
                continue

            try:
                callback(argument)

            except Exception as error:
                logger.error(f"Waiting on {self.title}: {error}", exc_info=True)
