"""Tests for the package detail-block formatting + version key."""
from plugin_management import browse_model

RAW = {
    "name": "scipy_analysis",
    "version": "0.1.0",
    "build": "pyh4616a5c_0",
    "size": 5485,
    "timestamp": 1782507668846,
    "subdir": "noarch",
    "noarch": "python",
    "fn": "scipy_analysis-0.1.0-pyh4616a5c_0.conda",
    "url": "https://prefix.dev/microdrop-plugins/noarch/scipy_analysis-0.1.0-pyh4616a5c_0.conda",
    "md5": "537115f431813e38d5599fe2df20b178",
    "sha256": "f4aa51f8f1d696e91c5d8155f3f75985b7d24d1eac8bbeef910884f04365e7c2",
    "depends": ["scipy >=1.10", "python >=3.11", "python *"],
}


def test_format_size():
    assert browse_model._format_size(5485) == "5.36 KiB"
    assert browse_model._format_size(None) == ""


def test_format_timestamp_utc():
    assert browse_model._format_timestamp(1782507668846) == "2026-06-26 21:01:08 UTC"
    assert browse_model._format_timestamp(None) == ""


def test_format_details_full():
    text = browse_model.format_details(RAW)
    assert "scipy_analysis-0.1.0-pyh4616a5c_0" in text   # header (fn w/o .conda)
    assert "scipy_analysis" in text
    assert "0.1.0" in text
    assert "5.36 KiB" in text
    assert "2026-06-26 21:01:08 UTC" in text
    assert "Dependencies:" in text
    assert " - scipy >=1.10" in text
    assert "f4aa51f8f1d696e91c5d8155f3f75985b7d24d1eac8bbeef910884f04365e7c2" in text


def test_format_details_missing_fields_no_crash():
    text = browse_model.format_details({"name": "x"})
    assert "x" in text  # does not raise; blank size/timestamp


def test_version_key_orders():
    assert browse_model._version_key("0.2.0") > browse_model._version_key("0.1.0")
    assert browse_model._version_key("1.0") > browse_model._version_key("0.9.9")
