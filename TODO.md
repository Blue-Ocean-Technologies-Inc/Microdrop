# TODO

### dropbot_status

- Update status values 2 times a second. Currently it updates on every message, which is connected directly to the hardware proxy signal, which updates 10 times a second, and is annoying to read. This can probably be done with a QTimer singleshot, similar to how I debounce device viwer state updates in the device_view_pane.

### device_viewer

- Implement find liquid. If in realtime mode, this means turning on the actual electrodes. If not, this means simply highlighting them (we will need a new electrode color in the draw function, similar to channel-edit mode)

- Turn on realtime mode for a small time when measuring liquid/filler capacitance so that the user doesn't need to do so manually.

### Build 

- Using just conda on Windows, it doesn't seem to find the correct DLLs. On linux (as seen in DOCS.md) this is solved by setting LD_LIBRARY_PATH to point to the conda lib folder. The relevant folder for Windows is DLLs (in the conda env directory for microdrop), so I imagine something similar needs to be done. I also found success weirdly enough by installing micromamba using Git Bash on Windows (on the Lenovo computer). The environment was very nonstandard though, so I recommend just trying a Windows native shell unless it doesn't work. To see the last build I did find microdrop on the Desktop and check dist for an exe. Everything except video recoding saving works (couldn't get ffmpeg to be bundled properly)

- Not sure if we want to build a single binary executable on the pi, but if so porting the build script to that

- Mac support

### Environment

- Pyside 6.9.2 fixes the pyqtgraph crash so make sure 6.9.1 isn't installed (for pip and conda on arm64 the pyside versions are very behind so something to keep in mind)