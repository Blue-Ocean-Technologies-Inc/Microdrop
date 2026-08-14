"""Portable Dropbot smoke test: no Redis, no GUI, no dramatiq — just
the vendored driver, straight over serial. Answers one question per
step: can we connect, and do the basic commands answer?

Run from ``src/``::

    pixi run python examples/portable_dropbot_smoke_test.py
    pixi run python examples/portable_dropbot_smoke_test.py --port COM7
    pixi run python examples/portable_dropbot_smoke_test.py \\
        --port /dev/ttyAMA10 --actuate --channels 0 1 --light 40

Safe by default: reads only (login, versions, status, motor
positions/homed). Nothing moves and no HV is applied unless
``--actuate`` (low voltage by default) or ``--light`` is passed.
"""
import argparse
import sys

from serial.tools import list_ports

from portable_dropbot_controller.driver.session import DropletBotSession

results = []


def step(name, func):
    """Run one check; a failure is reported and recorded, never a
    traceback that kills the remaining checks."""
    try:
        value = func()
        print(f"[PASS] {name}" + (f": {value}" if value is not None
                                  else ""))
        results.append((name, True))
        return value
    except Exception as error:
        print(f"[FAIL] {name}: {error}")
        results.append((name, False))
        return None


def find_port(baud):
    """First port whose login handshake answers, USB-style ports
    first (single-baud probe, same policy as the app's monitor)."""
    present = [port.device for port in list_ports.comports()]
    ordered = ([p for p in present if "USB" in p.upper()
                or "ACM" in p.upper() or p.upper().startswith("COM")]
               + [p for p in present if "USB" not in p.upper()
                  and "ACM" not in p.upper()
                  and not p.upper().startswith("COM")])
    print(f"Ports present: {ordered or 'none'}")
    for port in ordered:
        probe = DropletBotSession()
        try:
            # connect(autodetect=False) returns True on port OPEN
            # (legacy driver behavior); .connected is the login truth.
            if probe.connect(port=port, baudrate=baud,
                             autodetect=False) and probe.connected:
                probe.disconnect()
                return port
        except Exception:
            pass
        finally:
            try:
                probe.disconnect()
            except Exception:
                pass
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Portable Dropbot connection/command smoke test.")
    parser.add_argument("--port", help="Serial port (e.g. COM7, "
                        "/dev/ttyUSB0). Omit to scan.")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--no-autodetect", action="store_true",
                        help="Try only --baud instead of the driver's "
                             "baud whitelist.")
    parser.add_argument("--actuate", action="store_true",
                        help="Also test HV + electrode actuation "
                             "(applies voltage!).")
    parser.add_argument("--channels", type=int, nargs="+",
                        default=[0], help="Channels for --actuate.")
    parser.add_argument("--voltage", type=int, default=50,
                        help="HV amplitude for --actuate (V).")
    parser.add_argument("--frequency", type=int, default=10_000,
                        help="HV frequency for --actuate (Hz).")
    parser.add_argument("--light", type=int,
                        help="Also set the illumination LED to this "
                             "brightness (%%).")
    args = parser.parse_args()

    port = args.port or find_port(args.baud)
    if not port:
        print("No port answered the login handshake. Is the board "
              "powered? On a Pi, is the serial console disabled?")
        return 1
    print(f"Using port: {port}")

    session = DropletBotSession()

    def _connect():
        session.connect(port=port, baudrate=args.baud,
                        autodetect=not args.no_autodetect)
        if not session.connected:
            raise ConnectionError(
                "port opened but neither board answered login")
        return f"signal={session.uart.sig_board_connected} " \
               f"motor={session.uart.motor_board_connected}"

    if not step("connect (login handshake)", _connect):
        return 1

    step("firmware versions", lambda: session.version)
    step("board UID", lambda: session.uart.read_uid())
    step("board channels", lambda: session.uart.board_channels)
    status = step("status read", lambda: session.status)
    if status:
        print(f"       signal: {status.get('signal')}")
        print(f"       motor:  {status.get('motor')}")
    step("motor positions", lambda: session.uart.getMotorPositions())
    step("motors homed", lambda: session.uart.queryMotorHomed())

    if args.light is not None:
        # setLEDIntensity takes the firmware's raw 0-255 byte.
        step(f"light intensity {args.light}%",
             lambda: session.uart.setLEDIntensity(
                 round(int(args.light) * 255 / 100),
                 fluorescence=False))

    if args.actuate:
        step(f"set actuation {args.voltage} V @ {args.frequency} Hz",
             lambda: session.set_actuation(int(args.voltage),
                                           int(args.frequency)))
        step(f"actuate channels {args.channels}",
             lambda: session.actuate_channels(list(args.channels)))
        step("active capacitance",
             lambda: session.measure_active_capacitance())
        step("clear channels", lambda: session.clear_channels())

    step("disconnect", lambda: session.disconnect())

    failed = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks "
          f"passed" + (f"; FAILED: {', '.join(failed)}" if failed
                       else " — all good."))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
