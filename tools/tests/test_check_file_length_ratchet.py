# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Pure unit tests for tools/check_file_length_ratchet.py (#643).

The module is loaded from its file path rather than imported as a package
(``tools/`` isn't one of the plugin packages the import-linter contract
covers), so these tests need neither git nor a real checkout.
"""

# Standard library imports.
import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent.parent / "check_file_length_ratchet.py"
_spec = importlib.util.spec_from_file_location("check_file_length_ratchet", MODULE_PATH)
ratchet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ratchet)


def test_is_excluded_skips_test_and_demo_directories():
    assert ratchet.is_excluded("device_viewer/tests/test_zones.py")
    assert ratchet.is_excluded(
        "pluggable_protocol_tree/tests_with_redis_server_need/test_x.py"
    )
    assert ratchet.is_excluded("examples/demos/zones_demo/canvas.py")


def test_is_excluded_leaves_production_files_alone():
    assert not ratchet.is_excluded("device_viewer/views/device_view_dock_pane.py")
    assert not ratchet.is_excluded("microdrop_application/dialogs/test_dialogs.py")


def test_classify_growth_past_baseline_is_flagged():
    finding = ratchet.classify("god_file.py", 550, 500)

    assert finding == ("growth", "god_file.py", 550, 500)


def test_classify_shrink_below_baseline_is_informational():
    finding = ratchet.classify("shrinking_file.py", 450, 500)

    assert finding == ("shrink", "shrinking_file.py", 450, 500)


def test_classify_unchanged_length_is_silent():
    assert ratchet.classify("steady_file.py", 500, 500) is None


def test_classify_new_file_over_threshold_warns():
    finding = ratchet.classify("new_file.py", 600, None)

    assert finding == ("new_over_threshold", "new_file.py", 600, None)


def test_classify_new_file_under_threshold_is_silent():
    assert ratchet.classify("small_new_file.py", 50, None) is None


def test_format_finding_growth_warns_while_not_blocking():
    message = ratchet.format_finding(
        ("growth", "god_file.py", 550, 500), blocking=False
    )

    assert "[WARN]" in message
    assert "god_file.py: 550 lines, baseline is 500 (+50)" in message
    assert "warning-only for one release" in message


def test_format_finding_growth_fails_once_blocking():
    message = ratchet.format_finding(("growth", "god_file.py", 550, 500), blocking=True)

    assert "[FAIL]" in message
    assert "warning-only for one release" not in message


def test_format_finding_shrink_points_at_update_mode():
    message = ratchet.format_finding(
        ("shrink", "shrinking_file.py", 450, 500), blocking=False
    )

    assert "[INFO]" in message
    assert "--update" in message


def test_check_files_growth_fails_only_when_blocking(tmp_path, monkeypatch):
    monkeypatch.setattr(ratchet, "REPO_ROOT", tmp_path)
    grown = tmp_path / "grown.py"
    grown.write_text(
        "\n".join(f"line {i}" for i in range(550)) + "\n", encoding="utf-8"
    )
    baseline = {"grown.py": 500}

    findings, exit_code = ratchet.check_files(["grown.py"], baseline, blocking=True)
    assert findings == [("growth", "grown.py", 550, 500)]
    assert exit_code == 1

    findings, exit_code = ratchet.check_files(["grown.py"], baseline, blocking=False)
    assert findings == [("growth", "grown.py", 550, 500)]
    assert exit_code == 0


def test_check_files_shrink_never_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(ratchet, "REPO_ROOT", tmp_path)
    shrunk = tmp_path / "shrunk.py"
    shrunk.write_text(
        "\n".join(f"line {i}" for i in range(400)) + "\n", encoding="utf-8"
    )
    baseline = {"shrunk.py": 500}

    findings, exit_code = ratchet.check_files(["shrunk.py"], baseline, blocking=True)

    assert findings == [("shrink", "shrunk.py", 400, 500)]
    assert exit_code == 0


def test_check_files_skips_excluded_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(ratchet, "REPO_ROOT", tmp_path)
    test_dir = tmp_path / "device_viewer" / "tests"
    test_dir.mkdir(parents=True)
    big_test_file = test_dir / "test_big.py"
    big_test_file.write_text(
        "\n".join(f"line {i}" for i in range(900)) + "\n", encoding="utf-8"
    )

    findings, exit_code = ratchet.check_files(
        ["device_viewer/tests/test_big.py"], baseline={}, blocking=True
    )

    assert findings == []
    assert exit_code == 0


def test_update_baseline_never_raises_an_existing_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(ratchet, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        ratchet, "BASELINE_PATH", tmp_path / "file_length_baseline.json"
    )
    grown = tmp_path / "grown.py"
    grown.write_text(
        "\n".join(f"line {i}" for i in range(600)) + "\n", encoding="utf-8"
    )
    ratchet.save_baseline({"grown.py": 500})
    monkeypatch.setattr(ratchet, "_tracked_py_files", lambda: ["grown.py"])

    ratchet.update_baseline()

    assert ratchet.load_baseline() == {"grown.py": 500}


def test_update_baseline_lowers_a_shrunk_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(ratchet, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        ratchet, "BASELINE_PATH", tmp_path / "file_length_baseline.json"
    )
    shrunk = tmp_path / "shrunk.py"
    shrunk.write_text(
        "\n".join(f"line {i}" for i in range(510)) + "\n", encoding="utf-8"
    )
    ratchet.save_baseline({"shrunk.py": 900})
    monkeypatch.setattr(ratchet, "_tracked_py_files", lambda: ["shrunk.py"])

    ratchet.update_baseline()

    assert ratchet.load_baseline() == {"shrunk.py": 510}


def test_update_baseline_drops_a_file_that_fell_under_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr(ratchet, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        ratchet, "BASELINE_PATH", tmp_path / "file_length_baseline.json"
    )
    small_now = tmp_path / "small_now.py"
    small_now.write_text(
        "\n".join(f"line {i}" for i in range(100)) + "\n", encoding="utf-8"
    )
    ratchet.save_baseline({"small_now.py": 900})
    monkeypatch.setattr(ratchet, "_tracked_py_files", lambda: ["small_now.py"])

    ratchet.update_baseline()

    assert ratchet.load_baseline() == {}


def test_update_baseline_adds_a_new_file_over_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr(ratchet, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        ratchet, "BASELINE_PATH", tmp_path / "file_length_baseline.json"
    )
    new_file = tmp_path / "new_file.py"
    new_file.write_text(
        "\n".join(f"line {i}" for i in range(700)) + "\n", encoding="utf-8"
    )
    ratchet.save_baseline({})
    monkeypatch.setattr(ratchet, "_tracked_py_files", lambda: ["new_file.py"])

    ratchet.update_baseline()

    assert ratchet.load_baseline() == {"new_file.py": 700}


def test_baseline_file_is_valid_json_sorted_by_path():
    baseline = json.loads(ratchet.BASELINE_PATH.read_text(encoding="utf-8"))

    assert list(baseline) == sorted(baseline)
    assert all(
        isinstance(count, int) and count > ratchet.THRESHOLD
        for count in baseline.values()
    )
