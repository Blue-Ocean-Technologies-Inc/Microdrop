# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A failing message handler is logged once, naming the handler and the
topic, with its traceback attached."""

# Standard library imports.
import logging

# Microdrop utils imports.
from microdrop_utils.dramatiq_controller_base import invoke_class_method


class FailingListener:
    """A listener whose handler raises."""

    def _on_step_triggered(self, message):
        raise ValueError(f"bad step {message}")


def test_a_failing_handler_is_logged_once_with_handler_topic_and_traceback(caplog):
    with caplog.at_level(logging.DEBUG):
        invoke_class_method(
            FailingListener(), "_on_step_triggered", "3", topic="protocol/step"
        )

    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]

    assert len(errors) == 1

    record = errors[0]

    assert "FailingListener._on_step_triggered" in record.getMessage()
    assert "protocol/step" in record.getMessage()
    assert isinstance(record.exc_info[1], ValueError)
    assert "bad step 3" in caplog.text
