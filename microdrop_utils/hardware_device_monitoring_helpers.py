import json
import re
import threading
import time

import serial
from serial.tools.list_ports import grep
from traits.api import Any, HasTraits, Str

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


class ClaimedPort(HasTraits):
    """A port claimed for a device, with the serial handle that has been
    open since the whoami probe identified it. Handing this handle to the
    device's proxy makes probe→connect atomic: the port is never released
    between identification and ownership, so nothing can grab it in
    between (and Windows' USB-CDC close→reopen latency never applies).
    """

    port = Str(desc="Serial port name, e.g. COM7")
    serial = Any(
        desc="serial.Serial handle open since the whoami probe identified "
             "the board")

    def __str__(self):
        return self.port

    def close(self):
        try:
            self.serial.close()
        except Exception:
            pass


def _probe_port(port, baudrate, timeout_s=WHOAMI_PROBE_WAIT_S,
                keep_open=False):
    """``(result, handle)``: result is a ``device_id`` string, ``None``
    (opened, no identity — older firmware), or ``PORT_BUSY`` (could not
    open). ``handle`` is the still-open serial port when ``keep_open`` and
    the board identified, else None (port closed). Probes are serialized
    in-process.

    Reads line by line until a WHOAMI frame parses or ``timeout_s`` elapses,
    so a reply that arrives late (board busy streaming) or lands split
    across reads is not lost the way a single fixed-delay read_all() loses
    a line truncated mid-JSON."""
    with _probe_lock:
        try:
            probe = serial.Serial(port, baudrate, timeout=0.2, write_timeout=2)
        except Exception as e:
            logger.debug(f"whoami probe: cannot open {port}: {e}")
            return PORT_BUSY, None
        keep = False
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
                    keep = keep_open
                    return device_id, (probe if keep_open else None)
        except Exception as e:
            logger.debug(f"whoami probe: read failed on {port}: {e}")
            return None, None
        finally:
            if not keep:
                try:
                    probe.close()
                except Exception:
                    pass
    return None, None


def probe_port_device_id(port, baudrate=115200) -> str | None:
    """Briefly open ``port``, send ``whoami``, and return the board's
    ``device_id`` (None if the port can't be opened or doesn't identify).

    Port of the legacy heater UI's Identify feature. Lets peripheral
    monitors tell apart boards that share a VID:PID (the heater and
    fluorescence boards are both Pico 2E8A:0005) before claiming a port.
    """
    result, _ = _probe_port(port, baudrate)
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


def claim_port_by_device_id(hwids, device_id_fragment, *,
                            min_unidentified_scans=1) -> ClaimedPort:
    """Claim the port of the board whose whoami ``device_id`` contains
    ``device_id_fragment``, searching all ports matching ``hwids`` by
    VID:PID. Returns a ClaimedPort whose serial handle has been open since
    the identifying probe — hand it to the device proxy so the port is
    never released (and up for grabs) between identification and
    connection.

    Ports that identify as some OTHER device are never claimed. Ports that
    cannot be OPENED are skipped entirely (busy: the other plugin's board or
    a probe in flight — the monitor's next scheduled scan retries them). If
    no port identifies with a matching id, falls back to a port that opened
    but did not identify (older firmware without whoami) so single-board
    setups keep working — with a warning, since the fallback cannot
    distinguish devices.

    ``min_unidentified_scans`` gates that fallback: a port is only claimed
    once it has stayed unidentified across that many consecutive calls for
    this ``device_id_fragment``. The default of 1 keeps one-shot semantics;
    the periodic peripheral monitors pass a higher value so one missed
    probe window on a busy board doesn't hand it to the wrong plugin.
    """
    unidentified = []
    seen_ports = set()
    for hwid in hwids:
        for port_info in grep(hwid):
            port = str(port_info.device)
            seen_ports.add(port)
            result, handle = _probe_port(port, 115200, keep_open=True)
            if result is PORT_BUSY:
                logger.debug(f"Port {port} busy; skipping this scan")
            elif result is None:
                unidentified.append(port)
            elif device_id_fragment in result:
                _note_port_identified(device_id_fragment, port)
                logger.info(f"Board '{result}' matched on port {port}")
                return ClaimedPort(port=port, serial=handle)
            else:
                _note_port_identified(device_id_fragment, port)
                logger.debug(
                    f"Port {port} identifies as '{result}' — not a "
                    f"'{device_id_fragment}' board; skipping")
                try:
                    handle.close()
                except Exception:
                    pass
    _prune_unidentified_state(device_id_fragment, seen_ports)
    for port in unidentified:
        misses = _note_port_unidentified(device_id_fragment, port)
        if misses < min_unidentified_scans:
            logger.debug(
                f"Port {port} unidentified for "
                f"{misses}/{min_unidentified_scans} scans; not yet eligible "
                f"for the '{device_id_fragment}' fallback")
            continue
        # The probe closed this port (only identified ports stay open), so
        # the fallback reopens it here. A failure just skips this scan: the
        # miss count is kept and the next scan retries.
        try:
            handle = serial.Serial(port, 115200, timeout=2, write_timeout=2)
        except Exception as e:
            logger.debug(f"Fallback could not reopen {port}: {e}")
            continue
        logger.warning(
            f"No port identified as a '{device_id_fragment}' board; falling "
            f"back to port {port} after {misses} scans with no whoami reply "
            f"(older firmware?)")
        return ClaimedPort(port=port, serial=handle)
    raise Exception(f"No '{device_id_fragment}' board found for hwids {hwids}")


def find_port_by_device_id(hwids, device_id_fragment, *,
                           min_unidentified_scans=1) -> str:
    """The port NAME of the board whose whoami ``device_id`` contains
    ``device_id_fragment`` (see claim_port_by_device_id for the search and
    fallback rules). The claimed handle is closed before returning — for
    one-shot callers like the firmware uploader that need the port free;
    the periodic monitors use claim_port_by_device_id instead to hand the
    open port straight to the proxy."""
    claimed = claim_port_by_device_id(
        hwids, device_id_fragment,
        min_unidentified_scans=min_unidentified_scans)
    claimed.close()
    return claimed.port


if __name__ == "__main__":
    hwids = ['VID:PID=16C0:0483']
    check_devices_available(hwids)
