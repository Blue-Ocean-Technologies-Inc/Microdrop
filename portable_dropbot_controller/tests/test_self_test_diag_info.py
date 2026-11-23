# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The hub's board diagnostics read: the DIAG_INFO reply decoded into the
SelfTestDiagInfo payload, busy and refused reads answered with an error,
and a run refusing it. Hardware-free, no Redis."""

# Standard library imports.
import struct
import threading
from types import SimpleNamespace

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import Any, Bool, List

# Microdrop package imports.
from portable_dropbot_controller.self_test_results import diag_info_fields
from portable_dropbot_controller.services import (
    portable_dropbot_self_test_state_mixin_service as state_mod,
)
from portable_dropbot_controller.services.portable_dropbot_self_test_mixin_service import (  # noqa: E501
    SELF_TEST_ALLOWED_TOPICS,
)
from portable_dropbot_self_tests.consts import (
    PREFLIGHT_BOARD_BUSY_ERROR,
    SELF_TEST_DIAG_INFO_READ,
    SelfTestDiagInfo,
)

#: A main loop 31 s silent: past the IWDG kicker's 30 s limit.
STALLED_MS = 31000


def _diag_reply(main_loop_ms=1200, asserts=0):
    """A DIAG_INFO reply in the firmware's big-endian layout."""
    header = struct.pack(">II24sBI", asserts, 77, b"tempctrl_run", 1, 90500)
    ages = [main_loop_ms, 800, 0xFFFFFFFF, 50]
    alive = struct.pack(f">B{len(ages)}I", len(ages), *ages)
    threads = struct.pack(">B", 1) + struct.pack(">8sBBHH", b"main", 3, 10, 2048, 512)

    return SimpleNamespace(raw=header + alive + threads)


def test_a_reply_becomes_the_text_report_and_the_parsed_fields():
    fields = diag_info_fields(_diag_reply())
    diagnostics = fields["diagnostics"]

    assert fields["stalled_sources"] == []
    assert "IWDG running" in fields["text"]
    assert diagnostics["uptime_ms"] == 90500
    assert diagnostics["alive_age_ms"]["tempctrl 1"] is None
    assert diagnostics["threads"][0]["name"] == "main"
    SelfTestDiagInfo(**fields)


def test_a_stalled_source_is_named():
    fields = diag_info_fields(_diag_reply(main_loop_ms=STALLED_MS, asserts=2))

    assert fields["stalled_sources"] == ["main loop"]
    assert "STALLED" in fields["text"]
    assert "tempctrl_run:77" in fields["text"]


def test_no_reply_or_a_short_one_is_an_error():
    assert "no DIAG_INFO reply" in diag_info_fields(None)["error"]
    assert "not understood" in diag_info_fields(SimpleNamespace(raw=b"\0"))["error"]


def test_a_run_refuses_the_diagnostics_read():
    assert SELF_TEST_DIAG_INFO_READ not in SELF_TEST_ALLOWED_TOPICS


# --------------------------------------------------------------------- #
# The request handler                                                   #
# --------------------------------------------------------------------- #


class _Controller(state_mod.PortableDropbotSelfTestStateMixinService):
    """The state mixin plus the controller members the read uses."""

    proxy = Any()
    portable_dropbot_connection_active = Bool(True)
    _proxy_lock = Any()
    contexts = List()

    def __proxy_lock_default(self):
        return threading.RLock()

    def _proxy_call(self, context, call, serialize=True):
        self.contexts.append(context)

        with self._proxy_lock:
            return True, call()


@pytest.fixture
def published(monkeypatch):
    replies = []
    monkeypatch.setattr(
        state_mod,
        "self_test_diag_info_publisher",
        SimpleNamespace(
            publish=lambda reply: replies.append(SelfTestDiagInfo(**reply))
        ),
    )

    return replies


def _controller(reply):
    return _Controller(
        proxy=SimpleNamespace(sig=SimpleNamespace(diag_info=lambda: reply))
    )


def test_a_read_publishes_the_diagnostics(published):
    _controller(_diag_reply()).on_self_test_diag_info_read_request("")

    assert len(published) == 1
    assert published[0].text and not published[0].error


def test_a_held_lock_answers_busy_without_reading(published):
    controller = _controller(_diag_reply())
    held = threading.Event()
    release = threading.Event()

    def hold():
        with controller._proxy_lock:
            held.set()
            release.wait(5)

    holder = threading.Thread(target=hold)
    holder.start()
    held.wait(5)

    try:
        controller.on_self_test_diag_info_read_request("")
    finally:
        release.set()
        holder.join(5)

    assert [reply.error for reply in published] == [PREFLIGHT_BOARD_BUSY_ERROR]
    assert controller.contexts == []


def test_a_refused_read_still_gets_its_reply(published):
    controller = _controller(_diag_reply())

    controller._on_request_refused(
        SELF_TEST_DIAG_INFO_READ, "", "Portable Dropbot is disconnected"
    )

    assert [reply.error for reply in published] == ["Portable Dropbot is disconnected"]
