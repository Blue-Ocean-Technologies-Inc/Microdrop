"""compute_update_report is a pure function — these run Qt-free."""
from plugin_management.update_model import compute_update_report


def _pkg(name, version):
    return {"name": name, "version": version}


OLD = [_pkg("heater-microdrop-plugin", "1.0.0"),
       _pkg("magnet-microdrop-plugin", "1.0.0")]
NEW = [_pkg("heater-microdrop-plugin", "1.0.0"),
       _pkg("heater-microdrop-plugin", "1.0.2"),
       _pkg("magnet-microdrop-plugin", "1.0.0"),
       _pkg("shiny-new-plugin", "0.1.0")]


def test_update_detected_for_installed_older_version():
    report = compute_update_report(
        OLD, NEW, {"heater-microdrop-plugin": "1.0.0"})
    assert report.updates == [
        ("heater-microdrop-plugin", "1.0.0", "1.0.2")]


def test_no_update_when_installed_is_current_or_newer():
    report = compute_update_report(
        OLD, NEW, {"heater-microdrop-plugin": "1.0.2",
                   "magnet-microdrop-plugin": "2.0.0"})
    assert report.updates == []


def test_new_plugin_is_absent_from_old_cache_and_not_installed():
    report = compute_update_report(OLD, NEW, {})
    assert report.new_plugins == [("shiny-new-plugin", "0.1.0")]


def test_first_launch_baseline_reports_no_new_plugins():
    report = compute_update_report([], NEW, {"heater-microdrop-plugin": "1.0.0"})
    assert report.new_plugins == []
    assert report.updates == [
        ("heater-microdrop-plugin", "1.0.0", "1.0.2")]


def test_installed_but_gone_from_channel_is_ignored():
    report = compute_update_report(OLD, NEW, {"retired-plugin": "3.0.0"})
    assert all(name != "retired-plugin" for name, *_ in report.updates)


def test_has_content():
    assert not compute_update_report(OLD, OLD, {}).has_content
    assert compute_update_report(OLD, NEW, {}).has_content
