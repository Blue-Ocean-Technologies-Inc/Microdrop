import json
import re
import threading
import time

import serial
from serial.tools.list_ports import grep
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: How long the whoami probe waits for the firmware to answer (the legacy
#: heater UI's Identify feature used the same delay).
WHOAMI_PROBE_WAIT_S = 0.7

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


def device_id_from_whoami_output(text) -> str | None:
    """The ``device_id`` from a board's raw whoami output, or None.

    Boards in the heater firmware family reply to ``whoami`` with a
    ``§WHOAMI{json}`` line whose payload carries a per-board
    ``device_id`` (e.g. ``heater_board`` / ``fluo_board``).
    """
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("§WHOAMI"):
            brace = line.find("{")
            if brace < 0:
                continue
            try:
                return json.loads(line[brace:]).get("device_id")
            except Exception:
                continue
    return None


def _probe_port(port, baudrate):
    """``device_id`` string, ``None`` (opened, no identity — older firmware),
    or ``PORT_BUSY`` (could not open). Probes are serialized in-process."""
    with _probe_lock:
        try:
            probe = serial.Serial(port, baudrate, timeout=2, write_timeout=2)
        except Exception as e:
            logger.debug(f"whoami probe: cannot open {port}: {e}")
            return PORT_BUSY
        try:
            probe.reset_input_buffer()
            probe.write(b"whoami\n")
            probe.flush()
            time.sleep(WHOAMI_PROBE_WAIT_S)   # give the firmware time to reply
            text = probe.read_all().decode(errors="replace")
        except Exception as e:
            logger.debug(f"whoami probe: read failed on {port}: {e}")
            return None
        finally:
            try:
                probe.close()
            except Exception:
                pass
    return device_id_from_whoami_output(text)


def probe_port_device_id(port, baudrate=115200) -> str | None:
    """Briefly open ``port``, send ``whoami``, and return the board's
    ``device_id`` (None if the port can't be opened or doesn't identify).

    Port of the legacy heater UI's Identify feature. Lets peripheral
    monitors tell apart boards that share a VID:PID (the heater and
    fluorescence boards are both Pico 2E8A:0005) before claiming a port.
    """
    result = _probe_port(port, baudrate)
    return None if result is PORT_BUSY else result


def find_port_by_device_id(hwids, device_id_fragment) -> str:
    """The port of the board whose whoami ``device_id`` contains
    ``device_id_fragment``, searching all ports matching ``hwids`` by VID:PID.

    Ports that identify as some OTHER device are never claimed. Ports that
    cannot be OPENED are skipped entirely (busy: the other plugin's board or
    a probe in flight — the monitor's next scheduled scan retries them). If
    no port identifies with a matching id, falls back to the first port that
    opened but did not identify (older firmware without whoami) so
    single-board setups keep working — with a warning, since the fallback
    cannot distinguish devices.
    """
    unidentified = []
    for hwid in hwids:
        for port_info in grep(hwid):
            port = str(port_info.device)
            result = _probe_port(port, 115200)
            if result is PORT_BUSY:
                logger.info(f"Port {port} busy; skipping this scan")
            elif result is None:
                unidentified.append(port)
            elif device_id_fragment in result:
                logger.info(f"Board '{result}' matched on port {port}")
                return port
            else:
                logger.info(
                    f"Port {port} identifies as '{result}' — not a "
                    f"'{device_id_fragment}' board; skipping")
    if unidentified:
        logger.warning(
            f"No port identified as a '{device_id_fragment}' board; falling "
            f"back to unidentified port {unidentified[0]} (no whoami reply — "
            f"older firmware?)")
        return unidentified[0]
    raise Exception(f"No '{device_id_fragment}' board found for hwids {hwids}")


if __name__ == "__main__":
    hwids = ['VID:PID=16C0:0483']
    check_devices_available(hwids)
