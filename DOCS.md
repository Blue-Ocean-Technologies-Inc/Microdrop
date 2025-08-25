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

# Libraries

## dropbot.py

### SerialProxy.update_state(**kwargs)

Does not return anything useful as of writing. Updates *partially*, meaning that if a kwarg isn't specified it retains its previous value instead of having a defualt it's reverting to.

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

# Useful Enviroment Variables

#### USE_CV2=1

Set when you want to force the camera backend to use the opencv fallback even if it *can* use QMultimedia. Useful for testing/development.

#### DEBUG_QT_PLUGINS=1

Set to see debug logs from Qt plugins

#### QT_LOGGING_RULES="*=true"

Set when you want the maximal level for Qt-level debugs logs. These can be filtered down to your liking.

#### QT_FFMPEG_\[DECODING/ENCODING\]_HW_DEVICE_TYPES=

Set to blank when you want to force software encoding/decoding for Qt's FFMPEG backend. See [here](https://doc.qt.io/qt-6/advanced-ffmpeg-configuration.html)

# Building

We use pyinstaller to build the application into a single mostly statically linked executable. When porting to a new platform, you will probably have to modify pyinstaller.spec with some plaform specific file locations (which vary for conda/pip for example). The .spec file should be valid Python code so set syntax highlighting accordingly. Currently build for Windows/Linux works, the caveat being that cross-platform building isn't supported by pyinstaller (so you will need to build on 3 machines for 3 different platforms).

### Common Build Errors

#### Cannot import SSL / Cannot find version

This seems to be the first dynamically linked binary that pyinstaller looks for. On Linux, this might resolve to system SSL imports (not correct version) and on Windows this is likely just not found. This is a weird error since it comes from redis-py (python redis client), and the actual error get silenced for some reason in their code. Add "import ssl" to the run script so you can see the actual error.

The issue is that pyinstaller cannot find conda's dynamic imports, so the fix is to help it. On linux this is as simple as
```bash
LD_LIBRARY_PATH=/home/numberisnan/miniconda3/envs/microdrop/lib pyinstaller pyinstaller.spec -y
```
...replaced with the actual path to your env's lib folder (you can also just export it to set it for the rest of the shell session). In Windows this should be adding the similar path to PATH (keep in mind the the folder structure is different for Windows/Conda, so you might have to manually locate the folder with the correct DLL).

#### Cannot import libraries

Check that you are in the conda environment while building, then make sure that you are running the correct python. I found that paralell conda installations (miniconda3 and micromamba for example) have unpredictable behviour (python resolves to micromamba, but pyinstaller uses miniconda's python). To be explicit, first find a way to invoke the correct python binary (full path reference, PATH modification etc). For the latter you know you have this right when
```bash
where python # Windows
which python # Linux
```
resolves to the correct directory. 
 Then invoke pyinstaller as so
```bash
python -m PyInstaller pyinstaller.spec -y
```
