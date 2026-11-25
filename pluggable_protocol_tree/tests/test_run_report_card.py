# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A run report's card: quiet, one per report, Show opening the report and
its file name linking to its folder."""

# Standard library imports.
from pathlib import Path

# Microdrop package imports.
from notifications.consts import NotificationMessage, OpenPathAction
from pluggable_protocol_tree.consts import RUN_REPORTS_CATEGORY_ID
from pluggable_protocol_tree.services.logging.controller import run_report_card


def test_a_report_card_is_quiet_and_opens_its_report(tmp_path):
    report = tmp_path / "Experiment_1" / "reports" / "report_20261125_101500.html"
    message = NotificationMessage.model_validate(run_report_card(report))

    assert message.title == "Report generated"
    assert message.detail.splitlines() == [report.name, "Experiment Experiment_1"]
    assert not message.pop_up
    assert message.category_id == RUN_REPORTS_CATEGORY_ID
    assert isinstance(message.action, OpenPathAction)
    assert Path(message.action.path) == report
    assert [link.text for link in message.links] == [report.name]


def test_each_report_is_its_own_occurrence(tmp_path):
    first = run_report_card(tmp_path / "reports" / "report_1.html")
    second = run_report_card(tmp_path / "reports" / "report_2.html")

    assert first["occurrence"] != second["occurrence"]
