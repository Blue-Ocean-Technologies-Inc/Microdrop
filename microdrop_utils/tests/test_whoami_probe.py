"""Hardware-free tests for the whoami port probe.

The heater and fluorescence boards share a VID:PID (Pico 2E8A:0005), so the
monitors identify boards by their whoami ``device_id`` before claiming a
port. Serial/port enumeration is monkeypatched.
"""
from types import SimpleNamespace

import pytest

import microdrop_utils.hardware_device_monitoring_helpers as helpers
from microdrop_utils.hardware_device_monitoring_helpers import (
    device_id_from_whoami_output, find_port_by_device_id,
)

WHOAMI_HEATER = 'noise\n§WHOAMI{"uid": "e6614c30", "device_id": "heater_board"}\nmore'
WHOAMI_FLUO = '§WHOAMI{"uid": "a1b2c3d4", "device_id": "fluo_board"}'


# --- parsing --------------------------------------------------------------------

def test_device_id_parsed_from_whoami_frame():
    assert device_id_from_whoami_output(WHOAMI_HEATER) == "heater_board"
    assert device_id_from_whoami_output(WHOAMI_FLUO) == "fluo_board"


def test_no_frame_or_bad_json_gives_none():
    assert device_id_from_whoami_output("LED 0 set to 38% duty cycle") is None
    assert device_id_from_whoami_output("§WHOAMI{broken") is None
    assert device_id_from_whoami_output("") is None


# --- port selection --------------------------------------------------------------

@pytest.fixture
def ports(monkeypatch):
    """Fake the VID:PID port listing and per-port probe results."""
    state = {"ports": [], "ids": {}}
    monkeypatch.setattr(
        helpers, "grep",
        lambda hwid: [SimpleNamespace(device=p) for p in state["ports"]])
    monkeypatch.setattr(
        helpers, "probe_port_device_id",
        lambda port, baudrate=115200: state["ids"].get(port))
    return state


HWIDS = ["VID:PID=2E8A:0005"]


def test_matching_board_wins_regardless_of_order(ports):
    ports["ports"] = ["COM3", "COM4"]
    ports["ids"] = {"COM3": "fluo_board", "COM4": "heater_board"}
    assert find_port_by_device_id(HWIDS, "heater") == "COM4"
    assert find_port_by_device_id(HWIDS, "fluo") == "COM3"


def test_other_device_is_never_claimed(ports):
    # Only the OTHER board is plugged in: must raise, not steal its port.
    ports["ports"] = ["COM3"]
    ports["ids"] = {"COM3": "fluo_board"}
    with pytest.raises(Exception, match="No 'heater' board found"):
        find_port_by_device_id(HWIDS, "heater")


def test_unidentified_port_is_the_fallback(ports):
    # Older firmware without whoami (or a busy port): keep single-board
    # setups working via the first unidentified port.
    ports["ports"] = ["COM5"]
    ports["ids"] = {"COM5": None}
    assert find_port_by_device_id(HWIDS, "fluo") == "COM5"


def test_identified_match_beats_unidentified_fallback(ports):
    ports["ports"] = ["COM3", "COM4"]
    ports["ids"] = {"COM3": None, "COM4": "heater_board"}
    assert find_port_by_device_id(HWIDS, "heater") == "COM4"
