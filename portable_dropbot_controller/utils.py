
import serial.tools.list_ports as lsp
from .portable_dropbot_service import (
    SysStatusMotorBoard,
    SysStatusSignalBoard,
    AdcData,
)

# Common baud rates for DropletBot
COMMON_BAUD_RATES = [9600, 19200, 38400, 57600, 115200]


def decode_status_data(cmd, data):
    """Try to decode the mysterious 0x1204 status data"""
    if cmd >> 8 == 0x12:
        status = SysStatusSignalBoard.from_buffer_copy(data)
    elif cmd >> 8 == 0x11:
        status = SysStatusMotorBoard.from_buffer_copy(data)
    else:
        return "Unknown board"

    return status.to_dict()


def decode_adc_data(data):
    """Decode ADC data"""
    if len(data) == 0:
        return "No data"
    elif len(data) == 16:
        adc_data = AdcData.from_buffer_copy(data)
        return adc_data.to_dict()
    else:
        return f"Data: {data.hex(' ')} (length: {len(data)})"


def decode_login_response(data):
    """Decode login response data"""
    if len(data) == 0:
        return "No data"
    elif len(data) == 1:
        status = data[0]
        if status == 0:
            return "SUCCESS (status=0)"
        elif status == 1:
            return "FAILURE (status=1)"
        else:
            return f"Unknown status: {status}"
    else:
        return f"Data: {data.hex(' ')} (length: {len(data)})"


def list_serial_ports():
    """List all available serial ports."""
    print("Available serial ports:")
    ports = lsp.comports()

    if not ports:
        print("No serial ports found!")
        return []

    for i, port in enumerate(ports, 1):
        print(f"\n{i}. {port.device}")
        print(f"   Description: {port.description}")
        print(f"   Hardware ID: {port.hwid}")

    return [port.device for port in ports]


def select_port_interactive(ports):
    """Interactive port selection."""
    if not ports:
        print("\nNo ports found automatically.")
        port = input(
            "Enter serial port path manually (e.g., /dev/ttyUSB0 or COM3): "
        ).strip()
        return port if port else None

    if len(ports) == 1:
        port = ports[0]
        print(f"\nOnly one port found, using: {port}")
        return port

    print("\n" + "=" * 50)
    print("SELECT SERIAL PORT")
    print("=" * 50)

    while True:
        try:
            choice = input(
                f"\nEnter port number (1-{len(ports)}) or full path: "
            ).strip()

            if choice.startswith("/") or choice.startswith("COM"):
                return choice

            idx = int(choice) - 1
            if 0 <= idx < len(ports):
                return ports[idx]
            else:
                print(f"Please enter a number between 1 and {len(ports)}")
        except ValueError:
            print("Invalid input. Please enter a number or full path.")
        except KeyboardInterrupt:
            print("\nCancelled")
            return None


def select_baud_rate_interactive():
    """Interactive baud rate selection."""
    print("\n" + "=" * 50)
    print("SELECT BAUD RATE")
    print("=" * 50)

    print("\nCommon baud rates:")
    for i, baud in enumerate(COMMON_BAUD_RATES, 1):
        print(f"{i}. {baud} baud")

    print(f"{len(COMMON_BAUD_RATES) + 1}. Custom baud rate")

    while True:
        try:
            choice = input(
                f"\nEnter baud rate number (1-{len(COMMON_BAUD_RATES) + 1}): "
            ).strip()

            idx = int(choice) - 1
            if 0 <= idx < len(COMMON_BAUD_RATES):
                return COMMON_BAUD_RATES[idx]
            elif idx == len(COMMON_BAUD_RATES):
                # Custom baud rate
                custom_baud = input("Enter custom baud rate: ").strip()
                try:
                    baud = int(custom_baud)
                    if baud > 0:
                        return baud
                    else:
                        print("Baud rate must be positive.")
                except ValueError:
                    print("Invalid baud rate. Please enter a number.")
            else:
                print(
                    f"Please enter a number between 1 and {len(COMMON_BAUD_RATES) + 1}"
                )
        except ValueError:
            print("Invalid input. Please enter a number.")
        except KeyboardInterrupt:
            print("\nCancelled")
            return None

if __name__ == "__main__":
    main()
