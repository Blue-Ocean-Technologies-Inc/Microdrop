import json
import re
import threading
import time

import serial
from serial.tools.list_ports import grep
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Deadline for the whoami probe's read loop. The probe returns as soon as a
#: WHOAMI frame parses, so fast boards never wait this long; the headroom is
#: for boards busy streaming telemetry, whose reply can lag well past the
#: legacy Identify feature's 0.7 s delay.
WHOAMI_PROBE_WAIT_S = 1.5

#: Serializes whoami probes within this process: the heater and fluorescence
#: monitors run in the same backend, and concurrent probes of the same port
#: would make it look busy to one of them. Across processes the OS-exclusive
#: serial open provides the equivalent guarantee (the loser skips the port
#: until its next scan).
_probe_lock = threading.Lock()

#: Sentinel: the port could not be opened (busy — possibly the other
#: plugin's board or a probe in flight). Distinct from "opened but no
#: whoami reply" (older firmware), which is eligible for the fallback claim.
PORT_BUSY = object()


def check_connected_ports_hwid(id_to_screen, regexp='USB Serial'):
    """
    Check connected USB ports for a specific hardware id.
    """

    connected_ports = grep(regexp)
    valid_ports = []

    for port in connected_ports:
        pattern = re.compile(f".*{id_to_screen}.*")
        teensy = re.search(pattern, port.hwid)
        if bool(teensy):
            valid_ports.append(port)

    return valid_ports


def check_devices_available(hwids_to_check):
    """
    Method to find the USB port of device with hwid in hwids_to_check if it is connected.

    Note:
        Returns the first port name found if multiple ports are connected with devices having given hwid.
        Does not screen rest of provided hwids once port was found.
    """

    for hwid in hwids_to_check:
        valid_ports = check_connected_ports_hwid(hwid)
        # just picking first port, if multiple found.
        if len(valid_ports) > 0:
            port_name = str(valid_ports[0].device)
            # Indicate success by returning the port name
            logger.info(f'Device for hwids {hwids_to_check} found on port {port_name}')
            return port_name

        else:
            raise Exception(f'No device for hwids {hwids_to_check} found')


#: Prefix of a board's identity frame line: ``§WHOAMI{json}``.
WHOAMI_MARKER = "§WHOAMI"


def parse_whoami_line(line) -> dict | None:
    """The identity payload ({"uid", "device_id", ...}) from one WHOAMI
    frame line, or None.

    Boards in the heater firmware family reply to ``whoami`` with a
    ``§WHOAMI{json}`` line whose payload carries a per-board
    ``device_id`` (e.g. ``heater_board`` / ``fluo_board``).
    """
    line = line.strip()
    if not line.startswith(WHOAMI_MARKER):
        return None
    brace = line.find("{")
    if brace < 0:
        return None
    try:
        return json.loads(line[brace:])
    except Exception:
        return None


def device_id_from_whoami_output(text) -> str | None:
    """The ``device_id`` from a board's raw whoami output, or None."""
    for line in text.splitlines():
        identity = parse_whoami_line(line)
        if identity is not None:
            return identity.get("device_id")
    return None


def _probe_port(port, baudrate, timeout_s=WHOAMI_PROBE_WAIT_S):
    """``device_id`` string, ``None`` (opened, no identity — older firmware),
    or ``PORT_BUSY`` (could not open). Probes are serialized in-process.

    Reads line by line until a WHOAMI frame parses or ``timeout_s`` elapses,
    so a reply that arrives late (board busy streaming) or lands split
    across reads is not lost the way a single fixed-delay read_all() loses
    a line truncated mid-JSON."""
    with _probe_lock:
        try:
            probe = serial.Serial(port, baudrate, timeout=0.2, write_timeout=2)
        except Exception as e:
            logger.debug(f"whoami probe: cannot open {port}: {e}")
            return PORT_BUSY
        try:
            probe.reset_input_buffer()
            probe.write(b"whoami\n")
            probe.flush()
            deadline = time.monotonic() + timeout_s
            buf = b""
            while time.monotonic() < deadline:
                buf += probe.readline()
                device_id = device_id_from_whoami_output(
                    buf.decode(errors="replace"))
                if device_id is not None:
                    return device_id
        except Exception as e:
            logger.debug(f"whoami probe: read failed on {port}: {e}")
            return None
        finally:
            try:
                probe.close()
            except Exception:
                pass
    return None


def probe_port_device_id(port, baudrate=115200) -> str | None:
    """Briefly open ``port``, send ``whoami``, and return the board's
    ``device_id`` (None if the port can't be opened or doesn't identify).

    Port of the legacy heater UI's Identify feature. Lets peripheral
    monitors tell apart boards that share a VID:PID (the heater and
    fluorescence boards are both Pico 2E8A:0005) before claiming a port.
    """
    result = _probe_port(port, baudrate)
    return None if result is PORT_BUSY else result


#: Per-caller count of consecutive scans a port has failed to identify,
#: keyed (device_id_fragment, port). Lets the unidentified-port fallback in
#: find_port_by_device_id demand several misses in a row before claiming a
#: port: one missed probe window (board busy streaming) must not hand a
#: board to the wrong plugin. Process-local like _probe_lock.
_unidentified_miss_counts = {}
_unidentified_state_lock = threading.Lock()


def _note_port_identified(device_id_fragment, port):
    """The port answered with an identity (any identity) — it is not an
    older-firmware board, so its miss count is moot."""
    with _unidentified_state_lock:
        _unidentified_miss_counts.pop((device_id_fragment, port), None)


def _note_port_unidentified(device_id_fragment, port) -> int:
    """Bump and return the port's consecutive-miss count."""
    key = (device_id_fragment, port)
    with _unidentified_state_lock:
        count = _unidentified_miss_counts.get(key, 0) + 1
        _unidentified_miss_counts[key] = count
        return count


def _prune_unidentified_state(device_id_fragment, seen_ports):
    """Drop counts for ports this fragment's scan no longer sees (board
    unplugged, or the COM name reassigned) so stale misses can't carry over
    to whatever appears there next."""
    with _unidentified_state_lock:
        for key in [k for k in _unidentified_miss_counts
                    if k[0] == device_id_fragment and k[1] not in seen_ports]:
            del _unidentified_miss_counts[key]


def find_port_by_device_id(hwids, device_id_fragment, *,
                           min_unidentified_scans=1) -> str:
    """The port of the board whose whoami ``device_id`` contains
    ``device_id_fragment``, searching all ports matching ``hwids`` by VID:PID.

    Ports that identify as some OTHER device are never claimed. Ports that
    cannot be OPENED are skipped entirely (busy: the other plugin's board or
    a probe in flight — the monitor's next scheduled scan retries them). If
    no port identifies with a matching id, falls back to a port that opened
    but did not identify (older firmware without whoami) so single-board
    setups keep working — with a warning, since the fallback cannot
    distinguish devices.

    ``min_unidentified_scans`` gates that fallback: a port is only claimed
    once it has stayed unidentified across that many consecutive calls for
    this ``device_id_fragment``. The default of 1 keeps one-shot semantics
    (the firmware uploader's probe); the periodic peripheral monitors pass
    a higher value so one missed probe window on a busy board doesn't hand
    it to the wrong plugin.
    """
    unidentified = []
    seen_ports = set()
    for hwid in hwids:
        for port_info in grep(hwid):
            port = str(port_info.device)
            seen_ports.add(port)
            result = _probe_port(port, 115200)
            if result is PORT_BUSY:
                logger.debug(f"Port {port} busy; skipping this scan")
            elif result is None:
                unidentified.append(port)
            elif device_id_fragment in result:
                _note_port_identified(device_id_fragment, port)
                logger.info(f"Board '{result}' matched on port {port}")
                return port
            else:
                _note_port_identified(device_id_fragment, port)
                logger.debug(
                    f"Port {port} identifies as '{result}' — not a "
                    f"'{device_id_fragment}' board; skipping")
    _prune_unidentified_state(device_id_fragment, seen_ports)
    for port in unidentified:
        misses = _note_port_unidentified(device_id_fragment, port)
        if misses >= min_unidentified_scans:
            logger.warning(
                f"No port identified as a '{device_id_fragment}' board; "
                f"falling back to port {port} after {misses} scans with no "
                f"whoami reply (older firmware?)")
            return port
        logger.debug(
            f"Port {port} unidentified for {misses}/{min_unidentified_scans} "
            f"scans; not yet eligible for the '{device_id_fragment}' fallback")
    raise Exception(f"No '{device_id_fragment}' board found for hwids {hwids}")


if __name__ == "__main__":
    hwids = ['VID:PID=16C0:0483']
    check_devices_available(hwids)
