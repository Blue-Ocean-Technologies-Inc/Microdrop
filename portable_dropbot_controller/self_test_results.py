# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Self-test results: the SelfTestResult payload, the per-test JSON files,
the backend-owned unsaved-calibration state and the board diagnostics
payload. No Traits, Qt or messaging."""

# Standard library imports.
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

# Third-party imports.
from dropbot_portable import DropBotUart
from dropbot_portable import self_test as vendor_self_test
from dropbot_portable.diag_info import format_diag_info, parse_diag_info

# Microdrop package imports.
from microdrop_application.helpers import get_current_experiment_directory
from portable_dropbot_self_tests.consts import (
    UNSAVED_CALIBRATION,
    UNSAVED_PARTS,
    UNSAVED_TARE,
)

# Local imports.
from .self_test_choreography import CALIBRATION_TEST

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The experiment-directory folder holding one sub-folder per run.
SELF_TESTS_DIR_NAME = "self_tests"
CHANNELS_TEST = "test_channels"
#: CAP_CAL_SAVE status of a successful save.
CAP_CAL_SAVED_STATUS = 0


def run_stamp():
    """The run folder name: local time, sortable."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def experiment_run_directory(stamp):
    """``<experiment dir>/self_tests/<stamp>``; None when the experiment
    folder cannot be resolved (the run then writes no JSON copies)."""

    try:
        return Path(get_current_experiment_directory()) / SELF_TESTS_DIR_NAME / stamp
    except Exception as error:
        # Broad except: any preferences/Redis failure resolving the
        # experiment folder only costs the reference JSON copies.
        logger.error(f"Self-test results folder unavailable: {error}")

        return None


def run_id_echo(message):
    """Best-effort run_id off a request payload that failed validation."""

    try:
        raw = json.loads(str(message))
    except ValueError:
        return ""

    return str(raw.get("run_id", "")) if isinstance(raw, dict) else ""


def safe_verdicts(results):
    """``self_test.verdicts`` that never raises: a result the vendor judge
    cannot read gets no verdict instead of failing the run's report."""

    try:
        return vendor_self_test.verdicts(results)
    except Exception as error:
        logger.error(f"Self-test verdicts not computed: {error}", exc_info=True)

        return dict.fromkeys(results)


def strip_traceback(name, raw):
    """The result without its traceback, which goes to the log only."""
    traceback_text = raw.get("traceback")

    if traceback_text:
        logger.error(f"Self-test {name} raised:\n{traceback_text}")

    return {key: value for key, value in raw.items() if key != "traceback"}


def write_result_json(name, result, directory, stamp):
    """Save one test's result as the vendor's JSON file; returns its path as a
    string, "" when there is no directory or the write failed."""

    if directory is None:
        return ""

    try:
        return str(
            vendor_self_test.save_test_results_json(name, result, directory, stamp)
        )
    except Exception as error:
        # Broad except: the JSON copy is reference only; a full disk or a
        # vanished folder must not end the run.
        logger.error(f"Self-test {name} JSON not written to {directory}: {error}")

        return ""


def result_payload(run_id, name, result, results_path):
    """The SelfTestResult message for one finished test."""
    duration = result.get("duration")

    return {
        "run_id": run_id,
        "name": name,
        "title": vendor_self_test.test_title(name),
        "verdict": safe_verdicts({name: result}).get(name),
        "duration": None if duration is None else float(duration),
        "utc_timestamp": str(result.get("utc_timestamp", "")),
        "error": str(result.get("error", "")),
        "cancelled": bool(result.get("cancelled", False)),
        "restore_errors": [str(error) for error in result.get("restore_errors", [])],
        "result": vendor_self_test._to_jsonable(result),
        "results_path": results_path,
    }


def unsaved_parts(results, previous):
    """The RAM-only calibration parts after a run.

    A test that captured a part replaces whatever the board held before (it
    is unsaved unless the test reports it saved); a part no test of this run
    captured keeps its previous state.
    """
    unsaved = set(previous)
    calibration = results.get(CALIBRATION_TEST)
    channels = results.get(CHANNELS_TEST)

    if isinstance(calibration, dict) and calibration.get("cap_calibrate"):
        if calibration.get("cap_calibrate_saved") is False:
            unsaved.add(UNSAVED_CALIBRATION)
        else:
            unsaved.discard(UNSAVED_CALIBRATION)

    tare = channels.get("tare_capture") if isinstance(channels, dict) else None

    if isinstance(tare, dict) and tare.get("ok"):
        if tare.get("saved"):
            unsaved.discard(UNSAVED_TARE)
        else:
            unsaved.add(UNSAVED_TARE)

    return [part for part in UNSAVED_PARTS if part in unsaved]


def cap_calibration_save_outcome(ok, status):
    """Decode a ``saveCapCalibration`` call's ``(ok, result)``.

    Returns
    -------
    tuple
        ``(SelfTestCalibrationSaved fields, error)``; error "" when saved.
    """
    fields = {}

    if not ok:
        text = str(status or "no reply")
    elif status is False:
        text = "signal board not logged in"
    elif status is None:
        text = "no reply (firmware before v1.7.0 saves it itself)"
    else:
        fields["calibration_status"] = int(status)
        text = DropBotUart.CAP_CAL_SAVE_STATUS.get(int(status), f"status {status}")

    fields["calibration_text"] = text
    saved = fields.get("calibration_status") == CAP_CAL_SAVED_STATUS

    return fields, "" if saved else f"feedback-cap calibration not saved: {text}"


def elec_tare_save_outcome(ok, saved):
    """Decode a ``saveElecTare`` call's ``(ok, result)`` like
    ``cap_calibration_save_outcome``."""

    if ok and saved is True:
        return {"tare_ok": True}, ""

    if not ok:
        why = str(saved or "no reply")
    elif saved is False:
        why = "signal board not logged in"
    else:
        why = "refused or no reply"

    return {"tare_ok": False}, f"electrode tare not saved: {why}"


def diag_info_fields(reply):
    """The SelfTestDiagInfo fields of a ``sig.diag_info()`` reply, parsed and
    formatted by the vendor's ``diag_info``; firmware without DIAG_INFO
    answers UNKNOWN, which the proxy returns as None."""

    if reply is None:
        return {"error": "no DIAG_INFO reply (the firmware may predate it)"}

    try:
        info = parse_diag_info(reply.raw)
    except ValueError as error:
        return {"error": f"DIAG_INFO reply not understood: {error}"}

    return {
        "text": format_diag_info(info),
        "stalled_sources": info.stalled_sources(),
        "diagnostics": vendor_self_test._to_jsonable(asdict(info)),
    }
