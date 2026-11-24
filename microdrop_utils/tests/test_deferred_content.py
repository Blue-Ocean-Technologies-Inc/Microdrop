# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Deferred content builds once; what waits on it runs when it is built, or
fails over when its build raises, and says why instead of loading."""

# Standard library imports.
from unittest.mock import patch

# Microdrop utils imports.
from microdrop_utils.deferred_content import (
    CONTENT_BUILT,
    CONTENT_FAILED,
    CONTENT_LOADING,
    DeferredContent,
)

LOGGER = "microdrop_utils.deferred_content.logger"


def _content(builds, error=None):
    def build():
        builds.append("built")

        if error is not None:
            raise error

        return f"content {len(builds)}"

    return DeferredContent(title="Log", build=build)


def test_content_starts_loading_and_says_so():
    content = _content([])

    assert content.state == CONTENT_LOADING
    assert content.content is None
    assert content.status_text == "Loading Log…"


def test_content_builds_once():
    builds = []
    content = _content(builds)

    content.build_content()
    content.build_content()

    assert builds == ["built"]
    assert content.state == CONTENT_BUILT
    assert content.content == "content 1"


def test_waiting_callbacks_run_in_order_once_built():
    content = _content([])
    order = []

    for name in ("first", "second"):
        content.when_built(lambda built, name=name: order.append((name, built)))

    assert order == []

    content.build_content()

    assert order == [("first", "content 1"), ("second", "content 1")]


def test_a_request_to_built_content_runs_at_once():
    content = _content([])
    content.build_content()
    applied = []

    content.when_built(applied.append)

    assert applied == ["content 1"]


def test_a_failed_build_is_logged_kept_and_reported():
    builds = []
    content = _content(builds, error=RuntimeError("no table"))
    failures = []
    content.when_built(lambda built: None, failures.append)

    with patch(LOGGER) as logger:
        content.build_content()
        content.build_content()

    logger.error.assert_called_once()
    assert builds == ["built"]
    assert content.state == CONTENT_FAILED
    assert content.error == "no table"
    assert "RuntimeError: no table" in content.error_traceback
    assert content.status_text == "Log could not be loaded: no table"
    assert failures == ["no table"]


def test_a_request_to_failed_content_fails_at_once():
    content = _content([], error=ValueError("bad"))

    with patch(LOGGER):
        content.build_content()

    failures = []
    content.when_built(lambda built: None, failures.append)

    assert failures == ["bad"]


def test_a_raising_callback_does_not_keep_the_others_from_running():
    content = _content([])
    applied = []

    def raise_error(built):
        raise RuntimeError("callback")

    content.when_built(raise_error)
    content.when_built(applied.append)

    with patch(LOGGER) as logger:
        content.build_content()

    logger.error.assert_called_once()
    assert applied == ["content 1"]


def test_the_content_is_in_before_the_callbacks_run():
    content = _content([])
    seen = []

    content.when_built(lambda built: seen.append((content.state, content.content)))
    content.build_content()

    assert seen == [(CONTENT_BUILT, "content 1")]
