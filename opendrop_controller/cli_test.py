#!/usr/bin/env python3
"""
Simple CLI to test OpenDrop hardware connection and electrode control.

Port: If --port is omitted, the script finds the OpenDrop by VID:PID (239A:800B,
e.g. Feather M0). Use --port to override (e.g. /dev/cu.usbmodem1234 or COM3).

Usage (from repo root):
  python -m opendrop_controller.cli_test --list-ports
  python -m opendrop_controller.cli_test [--port PORT] [--electrodes 0,1,2] [--demo]

Options:
  --list-ports       List available serial ports and exit.
  --port PORT        Override serial port (default: auto-detect by VID:PID).
  --electrodes N,M   Electrode indices to test in sequence (default: 0,1,2,5,10).
  --all-off          Send once with all electrodes off and exit.
  --demo             Cycle electrode 0 on/off a few times (overrides sequence).
  --read-timeout-ms  Response timeout in ms (default 500).
  --baud             Baud rate (default 115200).
"""

import argparse
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from serial.tools import list_ports  # noqa: E402

from opendrop_controller.consts import (  # noqa: E402
    DEFAULT_BAUD_RATE,
    DEFAULT_READ_TIMEOUT_MS,
    DEFAULT_SERIAL_TIMEOUT,
    NUM_ELECTRODES,
    OPENDROP_VID_PID,
)
from opendrop_controller.opendrop_serial_proxy import OpenDropSerialProxy  # noqa: E402
from opendrop_controller.port_discovery import find_opendrop_port  # noqa: E402

# Electrodes to test in sequence when no --electrodes / --all-off / --demo
DEFAULT_TEST_ELECTRODES = [0, 1, 2, 5, 10]
STEP_DELAY_S = 1.0


def list_serial_ports():
    """Print available serial ports."""
    ports = list(list_ports.comports())
    if not ports:
        print("No serial ports found.")
        return
    print("Available serial ports:")
    for p in ports:
        print(f"  {p.device}\t{p.description or ''}\t{p.hwid or ''}")


def resolve_port(port_arg: str | None) -> str:
    """
    Resolve port: if None or empty, find by OpenDrop VID:PID; else use port_arg
    (with simple prefix glob if * is present).
    """
    if not (port_arg or "").strip():
        return find_opendrop_port() or ""
    port_arg = port_arg.strip()
    if "*" not in port_arg:
        return port_arg
    return find_opendrop_port(port_hint=port_arg) or port_arg


def run_test(
    port: str,
    electrodes_on: list[int],
    all_off: bool,
    demo: bool,
    read_timeout_ms: int,
    baud: int,
) -> int:
    port = resolve_port(port)
    if not port:
        print(
            f"Error: No OpenDrop device found (VID:PID={OPENDROP_VID_PID}). "
            "Use --port to specify a port or --list-ports to list ports.",
            file=sys.stderr,
        )
        return 1

    proxy = OpenDropSerialProxy(
        port=port,
        baud_rate=baud,
        serial_timeout_s=DEFAULT_SERIAL_TIMEOUT,
    )
    try:
        print(f"Connecting to {port} at {baud} baud...")
        proxy.connect()
        print("Connected.")
    except Exception as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        return 1

    temperatures_c = [25, 25, 25]
    feedback_enabled = False

    def send_state():
        t = proxy.write_state(
            feedback_enabled=feedback_enabled,
            temperatures_c=temperatures_c,
            read_timeout_ms=read_timeout_ms,
        )
        if not t.get("connected"):
            print(
                "Warning: device did not respond in time "
                "(disconnected or wrong protocol)."
            )
        else:
            bid = t.get("board_id")
            if bid is not None:
                print(f"  Board ID: {bid}")
            for k in ("temperature_1", "temperature_2", "temperature_3"):
                v = t.get(k)
                if v is not None:
                    print(f"  {k}: {v}")
        return t

    try:
        if all_off:
            proxy.state_of_channels[:] = False
            print("Sending all electrodes OFF...")
            send_state()
            print("Done.")
            return 0

        # Sequence to test: use --electrodes if given, else default list
        to_test = electrodes_on if electrodes_on else DEFAULT_TEST_ELECTRODES
        to_test = [i for i in to_test if 0 <= i < NUM_ELECTRODES]

        if demo:
            print("Demo: toggling electrode 0 every 2 seconds (5 times)...")
            for _ in range(5):
                proxy.state_of_channels[:] = False
                proxy.state_of_channels[0] = True
                send_state()
                time.sleep(2)
                proxy.state_of_channels[0] = False
                send_state()
                time.sleep(2)
            print("Demo done.")
        else:
            # Test a few electrodes one at a time, then all off
            print(f"Testing electrodes: {to_test} (each {STEP_DELAY_S}s)...")
            for idx in to_test:
                proxy.state_of_channels[:] = False
                proxy.state_of_channels[idx] = True
                print(f"  ON = [{idx}]")
                send_state()
                time.sleep(STEP_DELAY_S)
            proxy.state_of_channels[:] = False
            print("  All OFF")
            send_state()

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        proxy.close()
        print("Disconnected.")


def main():
    ap = argparse.ArgumentParser(
        description="OpenDrop hardware CLI: list ports, connect, and control electrodes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--list-ports", action="store_true", help="List serial ports and exit.")
    ap.add_argument(
        "--port",
        type=str,
        default=None,
        metavar="PORT",
        help="Serial port (default: auto-detect by VID:PID 239A:800B).",
    )
    ap.add_argument(
        "--electrodes",
        type=str,
        metavar="N,M,...",
        default="",
        help="Electrode indices to test in sequence (default: 0,1,2,5,10).",
    )
    ap.add_argument("--all-off", action="store_true", help="Send all electrodes OFF once and exit.")
    ap.add_argument("--demo", action="store_true", help="Run short demo: toggle electrode 0 a few times.")
    ap.add_argument(
        "--read-timeout-ms",
        type=int,
        default=DEFAULT_READ_TIMEOUT_MS,
        help="Response timeout (ms).",
    )
    ap.add_argument("--baud", type=int, default=DEFAULT_BAUD_RATE, help="Baud rate.")
    args = ap.parse_args()

    if args.list_ports:
        list_serial_ports()
        return 0

    electrodes_on = []
    if not args.all_off and (args.electrodes or "").strip():
        for part in args.electrodes.replace(",", " ").split():
            try:
                electrodes_on.append(int(part))
            except ValueError:
                print(f"Invalid electrode index: {part}", file=sys.stderr)
                return 1

    return run_test(
        port=args.port,
        electrodes_on=electrodes_on,
        all_off=args.all_off,
        demo=args.demo,
        read_timeout_ms=args.read_timeout_ms,
        baud=args.baud,
    )


if __name__ == "__main__":
    sys.exit(main())
