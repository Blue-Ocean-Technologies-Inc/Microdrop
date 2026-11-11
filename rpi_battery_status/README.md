# RPi Battery Status Plugin

A status-bar battery icon for the portable rig. It reads the status file the
`rpi-battery-monitor` daemon writes on the rig's Raspberry Pi; clicking or
tapping the icon opens a panel with the full readings. Where no daemon runs
the icon stays grey.

## Turning it on and off

The icon is a managed plugin group, `rpi_battery_ui`, registered in
`BUILTIN_PLUGIN_GROUPS` (`plugin_management/consts.py`) rather than in a
static plugin list. Toggle it under **Tools > Manage Plugins > Available
Groups**; the choice is saved and honoured at the next start, and the icon
appears or disappears immediately.

Out of the box it is on only on the Pi (`microdrop_utils.system_config.is_rpi()`).
To try it on another machine, point `MICRODROP_RPI_BATTERY_STATUS_FILE` at a
status file and tick the group on.

## Layout

- `services/status_file_reader.py`: locates and parses the daemon's status file.
- `models/battery_status.py`: Qt-free battery model and the icon's derived state.
- `controllers/battery_status_controller.py`: polls the file into the model.
- `views/`: the status-bar icon and the details panel.
- `demos/battery_status_icon_demo.py`: the icon standalone.

The plugin publishes and subscribes to no topics.
