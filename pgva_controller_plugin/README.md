# PGVA Controller Plugin

This plugin provides ethernet communication and control capabilities for the Festo PGVA (Pressure and Vacuum Generator) device within the Microdrop application framework.

## Features

- **Ethernet Communication**: Uses Modbus TCP protocol for reliable communication with PGVA devices
- **Pressure Control**: Set and monitor pressure setpoints and actual values
- **Vacuum Control**: Set and monitor vacuum setpoints and actual values
- **Device Management**: Enable, disable, and reset PGVA devices
- **Status Monitoring**: Real-time status updates and error reporting
- **Dramatiq Integration**: Asynchronous message handling for responsive UI

## Architecture

The plugin follows the established Microdrop controller pattern:

```
pgva_controller_plugin/
├── __init__.py                    # Package initialization
├── consts.py                      # Constants and topic definitions
├── plugin.py                      # Plugin integration
├── pgva_controller_base.py        # Main controller class
├── interfaces/
│   └── i_pgva_controller_base.py  # Interface definition
└── services/
    └── pgva_ethernet_communication.py  # Ethernet communication layer
```

## Usage

### Basic Setup

1. **Import the plugin** in your application:
```python
from pgva_controller_plugin.plugin import PGVAControllerPlugin
```

2. **Create a controller instance**:
```python
from pgva_controller_plugin.pgva_controller_base import PGVAControllerBase

controller = PGVAControllerBase(
    device_ip="192.168.1.100",
    device_port="502",
    unit_id="1"
)
```

### Connecting to PGVA Device

```python
# Connect to PGVA device
publish_message(
    topic="pgva/requests/connect",
    message=json.dumps({
        "ip": "192.168.0.1",
        "port": 502,
        "unit_id": 0
    })
)
```

### Controlling Pressure and Vacuum

```python
# Set pressure threshold
publish_message(
    topic="pgva/requests/set_pressure",
    message=json.dumps({"pressure": 500})  # 500 mbar
)

# Set vacuum threshold
publish_message(
    topic="pgva/requests/set_vacuum",
    message=json.dumps({"vacuum": -500})  # -500 mbar
)

# Set output pressure
publish_message(
    topic="pgva/requests/set_output_pressure",
    message=json.dumps({"pressure": 200})  # 200 mbar
)

# Read current pressure
publish_message(topic="pgva/requests/get_pressure", message="")

# Read current vacuum
publish_message(topic="pgva/requests/get_vacuum", message="")
```

### Device Control

```python
# Enable device
publish_message(topic="pgva/requests/enable", message="")

# Disable device
publish_message(topic="pgva/requests/disable", message="")

# Reset device
publish_message(topic="pgva/requests/reset", message="")

# Get device status
publish_message(topic="pgva/requests/get_status", message="")
```

### Listening to Status Updates

```python
from microdrop_utils.dramatiq_pub_sub_helpers import subscribe_to_topic

# Listen for pressure updates
def on_pressure_updated(message):
    data = json.loads(message)
    print(f"Current pressure: {data['pressure']}")

subscribe_to_topic("pgva/signals/pressure_updated", on_pressure_updated)

# Listen for vacuum updates
def on_vacuum_updated(message):
    data = json.loads(message)
    print(f"Current vacuum: {data['vacuum']}")

subscribe_to_topic("pgva/signals/vacuum_updated", on_vacuum_updated)

# Listen for connection status
def on_connected(message):
    print("PGVA device connected")

def on_disconnected(message):
    print("PGVA device disconnected")

subscribe_to_topic("pgva/signals/connected", on_connected)
subscribe_to_topic("pgva/signals/disconnected", on_disconnected)
```

## Message Topics

### Request Topics (Send to these topics to control the device)

- `pgva/requests/connect` - Connect to PGVA device
- `pgva/requests/disconnect` - Disconnect from PGVA device
- `pgva/requests/set_pressure` - Set pressure setpoint
- `pgva/requests/set_vacuum` - Set vacuum setpoint
- `pgva/requests/get_pressure` - Read current pressure
- `pgva/requests/get_vacuum` - Read current vacuum
- `pgva/requests/get_status` - Read device status
- `pgva/requests/enable` - Enable device
- `pgva/requests/disable` - Disable device
- `pgva/requests/reset` - Reset device

### Signal Topics (Listen to these topics for status updates)

- `pgva/signals/connected` - Device connected
- `pgva/signals/disconnected` - Device disconnected
- `pgva/signals/pressure_updated` - Pressure value updated
- `pgva/signals/vacuum_updated` - Vacuum value updated
- `pgva/signals/status_updated` - Device status updated
- `pgva/signals/error` - Error occurred

## Configuration

### Default Settings

The plugin uses the following default settings (defined in `consts.py`):

```python
PGVA_DEFAULT_IP = "192.168.0.1"
PGVA_DEFAULT_PORT = 502  # Modbus TCP port
PGVA_DEFAULT_UNIT_ID = 0
```

### Modbus Register Addresses

The register addresses are based on the official PGVA documentation:

```python
# Input Parameters (Read-only)
PGVA_PRESSURE_ACTUAL_MBAR = 0x10E  # Current pressure in mbar
PGVA_VACUUM_ACTUAL_MBAR = 0x10D    # Current vacuum in mbar
PGVA_OUTPUT_PRESSURE_ACTUAL_MBAR = 0x10F  # Output pressure in mbar
PGVA_STATUS = 0x106                 # Device status (16 bits)

# Holding Parameters (Read/Write)
PGVA_PRESSURE_THRESHOLD_MBAR = 0x100F  # Pressure threshold in mbar
PGVA_VACUUM_THRESHOLD_MBAR = 0x100E    # Vacuum threshold in mbar
PGVA_OUTPUT_PRESSURE_MBAR = 0x1010     # Output pressure in mbar
PGVA_MANUAL_TRIGGER = 0x1011           # Manual trigger control
PGVA_DISABLE_PUMP = 0x1018             # Pump enable/disable
```

## Error Handling

The plugin provides comprehensive error handling:

- **Connection Errors**: Automatic retry logic and timeout handling
- **Communication Errors**: Graceful degradation and error reporting
- **Device Errors**: Status monitoring and error propagation

Errors are published to the `pgva/signals/error` topic with descriptive messages.

## Integration with Microdrop

The PGVA controller integrates seamlessly with the Microdrop application framework:

1. **Plugin System**: Uses Envisage plugin architecture
2. **Message Broker**: Integrates with Dramatiq for asynchronous messaging
3. **Logging**: Uses the Microdrop logging system
4. **Traits**: Uses Enthought Traits for reactive programming

## Example Application

See `examples/pgva_control_example.py` for a complete example of how to use the PGVA controller in a Microdrop application.

## Troubleshooting

### Common Issues

1. **Connection Timeout**: Check IP address and network connectivity
2. **Modbus Errors**: Verify register addresses and unit ID
3. **Permission Errors**: Ensure proper network access to the device

### Debug Mode

Enable debug logging to see detailed communication:

```python
import logging
logging.getLogger('pgva_controller_plugin').setLevel(logging.DEBUG)
```

## Contributing

When contributing to this plugin:

1. Follow the existing code patterns and architecture
2. Add appropriate error handling and logging
3. Update documentation for any new features
4. Test with actual PGVA hardware when possible

## License

This plugin is part of the Microdrop project and follows the same licensing terms.
