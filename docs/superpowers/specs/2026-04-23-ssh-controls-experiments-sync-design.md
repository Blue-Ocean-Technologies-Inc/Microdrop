# SSH-Controls Experiments Sync — Design

**Date:** 2026-04-23
**Branch:** `feat/remote-experiments-sync`
**Status:** Approved design, pending implementation plan

## Goal

Add a "Sync Remote Experiments" feature that pulls the remote backend's `Experiments/` folder to a local directory via `rsync` over SSH. The feature is triggered from the frontend, executed asynchronously on the backend via the existing Dramatiq pub/sub message router, and surfaced to the user with a loading indicator, completion status, and a timeout warning with a Quit option.

## Topology & Security

This feature needs an explicit trust-boundary model because rsync-over-SSH inherently pairs two hosts, and the wrong direction leaks private material.

**The pull model (chosen).** The machine running the Microdrop GUI (the "frontend" physical host) acts as the rsync **client** and initiates the transfer. It holds the SSH private key generated locally by the Key Portal. The remote Microdrop backend host stores only the matching public key in its `~/.ssh/authorized_keys`. rsync runs locally on the frontend host, pulling `Experiments/` from the backend host.

**The push model (rejected).** The alternative — backend as rsync client, pushing files to the frontend — would require (a) shipping the private key to the remote backend machine, (b) granting the backend write access to the frontend's filesystem, and (c) running an SSH server on the frontend host. All three are unacceptable security trade-offs for this application.

**Consequence for plugin placement.** The `ssh_controls` plugin is Dramatiq-worker style — it is not a UI plugin and has no physical-hardware dependency — but it must execute *on the frontend host*, because that is where the private key lives and where rsync must run. Putting it on the backend host would either fail (no private key) or force the push model (rejected above).

This motivates a new plugin category: **service plugins**.

### Service plugins — new concept

Up until now, plugins fell into two buckets in `examples/plugin_consts.py`:

| Category | Examples | Role |
| --- | --- | --- |
| Frontend | `MicrodropPlugin`, `DeviceViewerPlugin`, `ProtocolGridControllerUIPlugin` | Qt/Pyface UI. Must be in the GUI process. |
| Backend | `DropbotControllerPlugin`, `ElectrodeControllerPlugin` | Talk to physical hardware (DropBot). Must be on the host wired to the device. |

**Service plugins** are a third category: Dramatiq message-router workers that are **host-bound by user-trust context**, not by hardware or UI. They:

- Are not UI — no Qt widgets, no menu contributions. (UI counterparts live in a matching `*_ui` frontend plugin.)
- Do not depend on physical hardware (no DropBot proxy).
- Handle credentials or filesystem resources local to the user running the GUI (SSH keys, local directories, rsync binary, etc.).
- Must therefore run in the same process as the user's GUI — *never* on the remote backend host.

`ssh_controls` is the first member of this category. The new `SERVICE_PLUGINS` list in `plugin_consts.py` makes the classification explicit so future reviewers / plugin authors do not misfile analogous plugins into `BACKEND_PLUGINS`.

## Scope

This replaces the initial standalone-plugin approach on this branch (commits `1b3a9d3`, `d75befc`, `667decc`, `b99909d`). That scaffold is dropped. The work is absorbed into the existing `ssh_controls` (service) and `ssh_controls_ui` (frontend) plugins, reusing their MVC + ViewModel + Dramatiq listener pattern.

### Removals

- Delete directory `remote_experiments_sync/` entirely
- Remove `RemoteExperimentsSyncPlugin` import and list entry from `examples/plugin_consts.py`

### Additions

| Plugin | Change |
| --- | --- |
| `ssh_controls/` (service) | New `models.py` with `ExperimentsSyncRequest` (Pydantic) + `ExperimentsSyncRequestPublisher` (ValidatedTopicPublisher). New topics and handler in `service.py`. |
| `ssh_controls_ui/` (frontend) | New `sync_dialog/` subpackage (model + view_model + widget + dramatiq listener). New menu action registered alongside the Key Portal action. New topics in `consts.py`. |
| `examples/plugin_consts.py` | New `SERVICE_PLUGINS` list containing `SSHControlsPlugin`. Add `SSHUIPlugin` to `FRONTEND_PLUGINS`. Document the "service plugin" concept in a module-level comment. |
| `examples/run_device_viewer_pluggable.py` | Include `SERVICE_PLUGINS` in the combined plugin list (runs alongside frontend + backend). |
| `examples/run_device_viewer_pluggable_frontend.py` | Include `SERVICE_PLUGINS` in the plugin list (runs with the GUI, even when the backend is remote). |
| `examples/run_device_viewer_pluggable_backend.py` | Does **not** include `SERVICE_PLUGINS` — intentionally. |

No changes to `microdrop_utils/file_sync_helpers.py`. No changes to `ssh_controls/plugin.py` or `ssh_controls_ui/plugin.py` (both already contribute `ACTOR_TOPIC_DICT` which is the only touch point).

Note: neither `SSHControlsPlugin` nor `SSHUIPlugin` is currently registered in any run config — the plugins exist as files but were never wired up. The additions above include registering them for the first time, not just for the sync feature.

## Architecture

### Service — `ssh_controls/`

Classified as a **service plugin** (see Topology & Security). Runs in the GUI process, not on the remote Microdrop backend host.

**`ssh_controls/models.py`** (new):

```python
from pydantic import BaseModel
from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher


class ExperimentsSyncRequest(BaseModel):
    host: str
    port: int
    username: str
    identity_path: str   # absolute path to SSH private key
    src: str             # remote path, e.g. "user@host:~/.../Experiments/"
    dest: str            # local absolute path


class ExperimentsSyncRequestPublisher(ValidatedTopicPublisher):
    validator_class = ExperimentsSyncRequest

    def publish(self, *, host, port, username, identity_path, src, dest, **kw):
        super().publish({
            "host": host,
            "port": port,
            "username": username,
            "identity_path": identity_path,
            "src": src,
            "dest": dest,
        }, **kw)
```

This mirrors the `ElectrodeStateChangePublisher` pattern in `electrode_controller/models.py`. Plain `str`/`int` types are used in the Pydantic model (not `StrictStr`/`StrictInt`). Pydantic is required here because `ValidatedTopicPublisher.validator_class` expects a `BaseModel` subclass.

**`ssh_controls/consts.py`** (extended):

```python
# Request topic
SYNC_EXPERIMENTS_REQUEST = "ssh_service/request/sync_experiments"

# Response topics
SYNC_EXPERIMENTS_STARTED = "ssh_service/started/sync_experiments"
SYNC_EXPERIMENTS_SUCCESS = "ssh_service/success/sync_experiments"
SYNC_EXPERIMENTS_ERROR   = "ssh_service/error/sync_experiments"

ACTOR_TOPIC_DICT = {
    listener_name: [
        GENERATE_KEYPAIR,
        KEY_UPLOAD,
        SYNC_EXPERIMENTS_REQUEST,  # new
    ]
}

# Module-level convenience publisher (matches electrode_controller/consts.py style)
from ssh_controls.models import ExperimentsSyncRequestPublisher
experiments_sync_publisher = ExperimentsSyncRequestPublisher(topic=SYNC_EXPERIMENTS_REQUEST)
```

**`ssh_controls/service.py`** (extended) — new handler:

```python
def _on_sync_experiments_request(self, message):
    try:
        model = ExperimentsSyncRequest.model_validate_json(message)
    except ValidationError as e:
        publish_message(
            json.dumps({"title": "Invalid sync request", "text": str(e)}),
            SYNC_EXPERIMENTS_ERROR,
        )
        return

    publish_message(
        json.dumps({"message": "Sync started"}),
        SYNC_EXPERIMENTS_STARTED,
    )

    try:
        result = Rsync().sync(
            src=model.src,
            dest=model.dest,
            identity=model.identity_path,
            ssh_port=model.port,
            archive=True,
            partial=True,
            verbose=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            publish_message(
                json.dumps({"message": "Sync complete."}),
                SYNC_EXPERIMENTS_SUCCESS,
            )
        else:
            tail = (result.stderr or "")[-500:]
            publish_message(
                json.dumps({
                    "title": f"rsync exit {result.returncode}",
                    "text": tail,
                }),
                SYNC_EXPERIMENTS_ERROR,
            )
    except FileNotFoundError as e:
        publish_message(
            json.dumps({"title": "rsync executable not found", "text": str(e)}),
            SYNC_EXPERIMENTS_ERROR,
        )
    except Exception as e:
        logger.exception("Remote sync failed")
        publish_message(
            json.dumps({"title": "Unexpected error", "text": str(e)}),
            SYNC_EXPERIMENTS_ERROR,
        )
```

`Rsync().sync(...)` is blocking. The handler runs on a Dramatiq worker so it blocks one worker thread for the duration of the sync. This matches the existing `_on_key_upload_request` handler's convention in the same plugin.

### Frontend — `ssh_controls_ui/sync_dialog/`

New subpackage mirroring the Key Portal's MVC+ViewModel structure.

**`sync_dialog/model.py`** — Traits model holding dialog state:

```python
class SyncDialogModel(HasTraits):
    host = Str(os.getenv("REMOTE_HOST_IP_ADDRESS", ""))
    port = Int(int(os.getenv("REMOTE_SSH_PORT") or 22))
    username = Str(os.getenv("REMOTE_HOST_USERNAME", ""))
    key_name = Str("id_rsa_microdrop")
    remote_experiments_path = Str("~/Documents/Sci-Bots/Microdrop/Experiments/")
    dest = Str  # resolved at dialog open to ETSConfig.user_data / "Remote-Experiments"
    status = Str("Idle")
    in_progress = Bool(False)
```

Traits `Str`/`Int` are used here (not Pydantic), matching the existing `SSHControlModel` style.

**`sync_dialog/view_model.py`** — mediates View ↔ Dramatiq listener:

```python
class SyncDialogViewModelSignals(QObject):
    status_changed = Signal(str)
    enable_sync_button = Signal(bool)
    show_in_progress = Signal(bool)           # toggles spinner visibility
    show_timeout_warning = Signal()           # triggers QMessageBox
    show_message_box = Signal(str, str, str)  # type, title, text
    close_dialog = Signal()


class SyncDialogViewModel(HasTraits):
    model = Instance(SyncDialogModel)
    view_signals = Instance(SyncDialogViewModelSignals)
    name = "Sync Dialog View Model"

    # QTimer instance, set up in traits_init
    _timeout_timer = ...  # 60s single-shot

    @Slot()
    def sync_command(self): ...
    @Slot()
    def quit_command(self): ...

    # Dramatiq-triggered handlers (topic -> method name convention)
    def _on_sync_experiments_started_triggered(self, message): ...
    def _on_sync_experiments_success_triggered(self, message): ...
    def _on_sync_experiments_error_triggered(self, message): ...
```

`sync_command`:
1. Validates identity file exists at `~/.ssh/<key_name>`; if not, emits `show_message_box("error", ...)` and returns.
2. Resolves `dest = ETSConfig.user_data / "Remote-Experiments"`, creates parent dir if needed.
3. Builds `src = f"{username}@{host}:{remote_experiments_path}"` (trailing slash preserved so rsync copies contents).
4. Sets `in_progress=True`, emits `enable_sync_button(False)`, `show_in_progress(True)`, `status_changed("Request sent, waiting for backend...")`.
5. Starts 60s QTimer (single-shot).
6. Calls `experiments_sync_publisher.publish(host=..., port=..., ...)`. Any `pydantic.ValidationError` from the publisher is caught and surfaced via `show_message_box`, and the UI state is reset.

`quit_command`:
- Stops the timer. Sets `in_progress=False`. Emits `close_dialog`. Does not signal the backend; the running rsync will continue and its eventual result is ignored (logged only).

Dramatiq-triggered handlers:
- `_on_sync_experiments_started_triggered` → timer reset, status "Backend acknowledged, syncing..."
- `_on_sync_experiments_success_triggered` → stop timer, info box "Sync complete.", close dialog
- `_on_sync_experiments_error_triggered` → stop timer, error box with `{title, text}`, re-enable Sync button, clear `in_progress`

Each handler checks `in_progress` first — if the user already quit, just log and return.

**`sync_dialog/widget.py`** — `SyncDialogView(QWidget)`:
- Group 1 (editable): host / port / username / key_name (line edits, pre-populated from model)
- Group 2 (paths): remote experiments path (editable) and local dest (read-only label)
- Sync button + status label
- QProgressBar (indeterminate, shown only while `in_progress` via `show_in_progress` signal)

Timeout interaction: when `show_timeout_warning` fires, widget shows a `QMessageBox.warning` with "Keep Waiting" and "Quit" buttons. "Keep Waiting" restarts the timer for another 60s. "Quit" calls `view_model.quit_command`.

**`sync_dialog/dramatiq_listener.py`** — `SyncDialogListener`:

A second listener in the plugin, separate from `SSHControlUIListener`, so each dialog owns its own topic set (decision B). Same internals: `basic_listener_actor_routine(self.ui, message, topic)` dispatches to the matching `_on_{topic}_triggered` method on the ViewModel.

```python
class SyncDialogListener(HasTraits):
    ui = Instance(SyncDialogViewModel)
    dramatiq_listener_actor = Instance(dramatiq.Actor)
    name = sync_listener_name

    def traits_init(self):
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=sync_listener_name,
            class_method=self.listener_actor_routine,
        )

    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(self.ui, message, topic)
```

**`ssh_controls_ui/consts.py`** — add sync listener and route:

```python
from ssh_controls.consts import (
    ...,  # existing
    SYNC_EXPERIMENTS_STARTED,
    SYNC_EXPERIMENTS_SUCCESS,
    SYNC_EXPERIMENTS_ERROR,
)

sync_listener_name = f"{PKG}_sync_listener"

ACTOR_TOPIC_DICT = {
    listener_name: [ ... ],  # existing
    sync_listener_name: [
        SYNC_EXPERIMENTS_STARTED,
        SYNC_EXPERIMENTS_SUCCESS,
        SYNC_EXPERIMENTS_ERROR,
    ],
}
```

Since `ssh_controls_ui/plugin.py` already exposes `actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)`, the new listener is registered automatically — no plugin-class edits.

**`ssh_controls_ui/menus.py`** — add second action:

```python
class SyncDialogApp(QMainWindow):
    def __init__(self, main_widget):
        super().__init__()
        self.setWindowTitle("Sync Remote Experiments")
        self.setGeometry(150, 150, 480, 320)
        self.setCentralWidget(main_widget)


class ShowSyncRemoteExperimentsAction(Action):
    name = "Sync Remote &Experiments..."
    tooltip = "Pull the remote backend's Experiments/ folder locally via rsync over SSH."
    style = "window"

    def traits_init(self):
        self._window = None
        self.model = SyncDialogModel()
        self.view_model = SyncDialogViewModel(
            model=self.model,
            view_signals=SyncDialogViewModelSignals(),
        )
        self.listener = SyncDialogListener(ui=self.view_model)

    def perform(self, event):
        if self._window is not None:
            self._window.close()
        widget = SyncDialogView(view_model=self.view_model)
        widget.initialize_field_values(...)
        widget.connect_signals()
        self._window = SyncDialogApp(main_widget=widget)
        self._window.show()


def menu_factory():
    return SGroup(
        ShowSshKeyUploaderAction(),
        ShowSyncRemoteExperimentsAction(),
        id="remote_controls",
    )
```

## Message Flow

```
[User clicks Sync in SyncDialogView]
  └─► SyncDialogViewModel.sync_command()
       ├─ validate identity file, resolve src/dest
       ├─ start 60s QTimer
       ├─ emit status_changed("Request sent, waiting for backend...")
       └─ experiments_sync_publisher.publish(host, port, username, identity_path, src, dest)
            │ (Pydantic validation -> JSON -> Redis via Dramatiq message_router_actor)
            ▼
[Backend: ssh_controls_listener worker]
  └─► SSHService._on_sync_experiments_request(message)
       ├─ publish(SYNC_EXPERIMENTS_STARTED, {"message": "Sync started"})
       ├─ Rsync().sync(...)   [blocks worker]
       └─ publish(SUCCESS|ERROR, payload)
            │
            ▼
[Frontend: ssh_controls_ui_sync_listener]
  └─► SyncDialogViewModel._on_sync_experiments_{started,success,error}_triggered
       ├─ started  → reset timer, status update
       ├─ success  → stop timer, info box, close dialog
       └─ error    → stop timer, error box, re-enable Sync button

[60s timer fires without success/error]
  └─► show_timeout_warning -> QMessageBox "Keep Waiting | Quit"
       ├─ Keep Waiting → restart 60s timer, remain in progress
       └─ Quit         → stop timer, close dialog (backend keeps running; late results logged only)
```

## Error Handling

| Error | Where caught | Result |
| --- | --- | --- |
| `ValidationError` when publishing | `sync_command` | `show_message_box("error", ...)`, UI state reset |
| Missing identity file | `sync_command` (pre-publish) | `show_message_box("error", ...)`, no publish |
| Blank/invalid host/user/port fields | `sync_command` (pre-publish) | `show_message_box`, no publish |
| `ValidationError` in backend handler on `model_validate_json` | `_on_sync_experiments_request` | `SYNC_EXPERIMENTS_ERROR` with `{title, text}` |
| `FileNotFoundError` (rsync missing) | `_on_sync_experiments_request` | `SYNC_EXPERIMENTS_ERROR` |
| `rsync` non-zero exit | `_on_sync_experiments_request` | `SYNC_EXPERIMENTS_ERROR` with stderr tail |
| Unexpected exception in handler | `_on_sync_experiments_request` | `SYNC_EXPERIMENTS_ERROR` + `logger.exception(...)` |
| Late backend response after Quit | ViewModel handlers | `in_progress` gate: log-only |

## Testing

### Automated

- **Unit** — `ExperimentsSyncRequest` rejects payloads missing required fields; accepts a realistic payload. Pattern from `examples/tests/test_messaging_api.py`.
- **Unit** — `ExperimentsSyncRequestPublisher.publish(...)` with all fields produces a JSON payload matching the expected shape.
- **Integration** (under `examples/tests/tests_with_redis_server_need/`) — publish a sync request with `Rsync` monkeypatched to return a `CompletedProcess` with `returncode=0`; observe `SYNC_EXPERIMENTS_STARTED` then `SYNC_EXPERIMENTS_SUCCESS` in order. Then with a stub that raises `FileNotFoundError`; observe `SYNC_EXPERIMENTS_ERROR`.

### Manual

No automated UI test. Manual plan:
1. Run full app (`python examples/run_device_viewer_pluggable.py`).
2. Configure `.env` with remote host/user/port and upload key via Key Portal.
3. Open `Edit → Sync Remote Experiments...`, click Sync.
4. Verify: dialog shows "Request sent...", then "Backend acknowledged, syncing...", then closes on success with info box. Local `Remote-Experiments/` folder contains the remote's experiments.
5. Force timeout: point at an unreachable host, verify the "Keep Waiting | Quit" prompt appears after 60s and Quit closes the dialog cleanly.
6. Force error: use wrong identity path, verify error box with rsync stderr tail.

## Future Enhancement (Out of Scope)

- **Best-effort cancel.** Add `SYNC_EXPERIMENTS_CANCEL_REQUEST` topic. Backend tracks the running subprocess per in-flight request and, on cancel, calls `subprocess.terminate()`. Quit in the dialog would then publish cancel before closing. `partial=True` keeps partially-transferred files. Not in scope for v1.
- **Progress streaming.** Backend parses rsync stdout and publishes progress messages. Not in scope.
