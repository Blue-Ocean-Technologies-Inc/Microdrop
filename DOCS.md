# Application Components

### Frontend

All UI plugins, and the MessageRouterPlugin

### Backend

MessageRouterPlugin, ElectrodeControllerPlugin, DropbotControllerPlugin

### Message Router

The Message Router (found in message_router), Plugin A and B are all Envisage plugins.

When MessageRouterPlugin is loaded (from the run script, so only one instance/Envisage App), it creates a new  MessageRouterActor (found in microdrop_utils/dramatiq_pub_sub_helpers), which creates a MessageRouterData with a static random queue number (since its not referenced anywhere else im assuming its not used)

It then listens on that queue and for every (message, topic) pair it receives and propagates the messages to every subscriber to the topic. The idea is to hack dramatiq into a full pub/sub system, which does not support broadcast messages otherwise.

MessageRouterData keeps track of all of the pub/sub info, and provides the relevant methods to publish/listen

An example of how it works can be found in /examples/tests/tests_with_redis_server_need/test_message_router.py

### Dramatiq Controller

If you find any class methods of the form "_on_{topic}_triggered" in frontend code, with no referenced anywhere else in the codebase, its probably being triggered by microdrop_utils/dramatiq_controller_base.py. These trigger when Dramatiq detects a topic of that form for relevant classes.

### Dropbot Controller

Similar to the Dramatiq handlers, a callback of the form "on_{specific_sub_topic}_request" or "on_{specific_sub_topic}_signal" is called when the plugin receives a message for that topic (in MQTT-style terms, the final subtopic). "request" handlers are only run if a dropbot is connected. Relevant code is in dropbot_controller/dropbot_controller_base.py

The reason that the notation is different from the dramatiq controller is to differentiate between frontend handlers ('triggering' a view change on update) and backend handlers (relaying a 'request' to hardware). 

### DramatiqDropbotSerialProxy

A simple extension of the dropbot library's SerialProxy. All it does is publish CONNECTED and DISCONNECTED signals, binding them to the relevant proxy.monitor event hooks

### SVG Handler

In order to allow path tracing in the electrodes view, the coordinate of each electrode, "connection" information (namely what electrodes are neighbors), and channel numbers for each electrode must be maintained. The application makes heavy use of the metadata in the SVG file (viewable as an XML file if opened with a text editor) in order to achieve this. Below is an example of an electrode path in the SVG file
```svg
<ns0:path d="M 41.585362,68.4188 H 47.703471 V 62.300688 H 41.585362 Z" data-channels="13" id="electrode050" style="fill:#000000" ns2:connector-curvature="0" />
```
The data channel is stored in data-channels. The "center" is found by parsing and computing the path (in utils/dmf_utils.py, computing the mean of the vertices). Neighbors are found (in the same file) by scaling the electrodes and figuring out which ones touch (effectively a distance function extended to nonstandard shapes). This currently allows diagonal connections in the grid area which are not allowed.

Because of manual parsing, the application only allows certain kinds of SVGs. Notably, it does not support any form of curve (C, S, Q, T, A, etc) in the path (see manual parsing in svg_to_paths())

# Files/Folders

## /examples

Lots of run scripts for various components of the application.

### /examples/run_demo_dramatiq_pluggable.py

A simple demo that demonstrates Envisage services (using toy examples in /examples/toy_plugins) and dramatiq task dispatch/receiving. Useful for a full example of all imports/setup required.

### /examples/dropbot_device_monitoring_aps_dramatiq_scheduled.py

Imports functions from /microdrop_utils/broker_server_helpers.py that no longer exist. Is not imported anywhere so can safely be ignored.

### /examples/run_device_viewer_pluggable_dropbot_service_demo.py

Dummy plugin offering Envisage service

### /examples/run_device_viewer_pluggable_backend.py

Runs only the backend plugins, and tries to run the redis server

### /examples/run_device_viewer_pluggable_frontend.py

Runs only the frontend (GUI). Needs the redis server and backend to function properly

### /examples/run_dropbot_status_ui_singly.py

Runs only the plots and status widget, without the other usual pluins

# Tests

Most tests can be found in /examples/tests/. There are additional tests scattered around:
- /electrode_controller/tests

# Conda

### To create environment

```bash
conda env create -f environment.yml
```
or
```bash
micromamba env create -f environment.yml
```
### To delete environment

Remember to deactivate the conda env first

```bash
conda env remove -n microdrop --all
```
or
```bash
micromamba env remove -n microdrop
```

# Debugging

On Linux/Mac (probably) you can use strace on the device path itself to snoop all serial communication between a python process (the backend) and the dropbot. Logs are quite clean, and gives you good idea of what's actually being sent/recieved hardware side.

```bash
strace -s 256 -P <device path> -e trace=write,read -o trace.log -f python <script name>
```