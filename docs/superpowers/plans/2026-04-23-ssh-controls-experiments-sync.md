# SSH-Controls Experiments Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Sync Remote Experiments" feature to MicroDrop — rsync-over-SSH pull of the remote backend's `Experiments/` folder, triggered from a dialog in the existing `ssh_controls_ui` plugin.

**Architecture:** Extends existing `ssh_controls` (Dramatiq service, colocated with GUI) and `ssh_controls_ui` (Pyface UI) plugins. Introduces a third plugin category — `SERVICE_PLUGINS` in `examples/plugin_consts.py` — for Dramatiq workers that must colocate with the user's GUI process (trust-bound, not hardware-bound). Frontend is the rsync client (pull model); private keys never leave the GUI host.

**Tech Stack:** PySide6 (Qt widgets + QThread/QTimer), Traits/TraitsUI, Pyface/Envisage plugins, Dramatiq (Redis broker), Pydantic v2 for payload validation, existing `microdrop_utils.file_sync_helpers.Rsync`.

**Reference spec:** `docs/superpowers/specs/2026-04-23-ssh-controls-experiments-sync-design.md`

**Project-specific conventions:** Per the project's CLAUDE.md and user memory, the user runs tests/scripts manually (pixi env). The executor should implement + commit per task and pause at "run" steps for user verification. Multi-commit workflow: each task is its own commit with a descriptive message; never bulk-commit across tasks.

---

## Branch preparation

### Task 0: Reset branch to drop scaffold commits while preserving the design spec

The branch `feat/remote-experiments-sync` currently has four scaffold commits to discard, plus two spec commits to preserve:

```
b01522c  Spec: introduce SERVICE_PLUGINS category and topology section   KEEP
79a474c  Add SSH-controls experiments-sync design spec                   KEEP
b99909d  Register RemoteExperimentsSyncPlugin in FRONTEND_PLUGINS        DROP
667decc  Add SyncRemoteExperimentsAction menu entry                      DROP
d75befc  Add RemoteSyncWorker for off-thread rsync execution              DROP
1b3a9d3  Add remote_experiments_sync plugin scaffold                      DROP
22960d0  Merge pull request #373 ...                                      (main tip — keep)
```

**Files:**
- Modify: git history of `feat/remote-experiments-sync`

- [ ] **Step 1: Back up the spec commits onto a temporary branch**

```bash
git branch backup/spec-commits b01522c
```

- [ ] **Step 2: Reset current branch to the merge commit just before the scaffold work**

```bash
git reset --hard 22960d0
```

- [ ] **Step 3: Cherry-pick the two spec commits back onto the reset branch**

```bash
git cherry-pick 79a474c b01522c
```

- [ ] **Step 4: Verify the branch is clean and has only the spec commits ahead of main**

```bash
git log --oneline main..HEAD
```

Expected output:
```
<new-hash>  Spec: introduce SERVICE_PLUGINS category and topology section
<new-hash>  Add SSH-controls experiments-sync design spec
```

Also verify the `remote_experiments_sync/` directory is gone from the working tree:
```bash
ls remote_experiments_sync 2>&1
```
Expected: "No such file or directory" (or equivalent).

- [ ] **Step 5: Delete the backup branch now that the spec commits have been replayed**

```bash
git branch -D backup/spec-commits
```

---

## Backend — `ssh_controls/` additions

### Task 1: Add `ExperimentsSyncRequest` Pydantic model + publisher

**Files:**
- Create: `ssh_controls/models.py`
- Create: `examples/tests/test_ssh_controls_models.py`

- [ ] **Step 1: Write the failing unit tests**

Create `examples/tests/test_ssh_controls_models.py`:

```python
"""Unit tests for ssh_controls.models — ExperimentsSyncRequest validation."""

import pytest
from pydantic import ValidationError

from ssh_controls.models import ExperimentsSyncRequest, ExperimentsSyncRequestPublisher


VALID_PAYLOAD = {
    "host": "192.168.1.10",
    "port": 22,
    "username": "dropbot",
    "identity_path": "/home/user/.ssh/id_rsa_microdrop",
    "src": "dropbot@192.168.1.10:~/Documents/Sci-Bots/Microdrop/Experiments/",
    "dest": "/home/user/.microdrop/Remote-Experiments",
}


class TestExperimentsSyncRequest:

    def test_valid_payload_parses(self):
        model = ExperimentsSyncRequest.model_validate(VALID_PAYLOAD)
        assert model.host == "192.168.1.10"
        assert model.port == 22
        assert model.username == "dropbot"

    def test_missing_host_rejected(self):
        payload = dict(VALID_PAYLOAD)
        del payload["host"]
        with pytest.raises(ValidationError):
            ExperimentsSyncRequest.model_validate(payload)

    def test_missing_port_rejected(self):
        payload = dict(VALID_PAYLOAD)
        del payload["port"]
        with pytest.raises(ValidationError):
            ExperimentsSyncRequest.model_validate(payload)

    def test_missing_identity_path_rejected(self):
        payload = dict(VALID_PAYLOAD)
        del payload["identity_path"]
        with pytest.raises(ValidationError):
            ExperimentsSyncRequest.model_validate(payload)

    def test_missing_src_rejected(self):
        payload = dict(VALID_PAYLOAD)
        del payload["src"]
        with pytest.raises(ValidationError):
            ExperimentsSyncRequest.model_validate(payload)

    def test_missing_dest_rejected(self):
        payload = dict(VALID_PAYLOAD)
        del payload["dest"]
        with pytest.raises(ValidationError):
            ExperimentsSyncRequest.model_validate(payload)

    def test_non_int_port_rejected(self):
        payload = dict(VALID_PAYLOAD)
        payload["port"] = "not-a-number"
        with pytest.raises(ValidationError):
            ExperimentsSyncRequest.model_validate(payload)

    def test_json_round_trip(self):
        model = ExperimentsSyncRequest.model_validate(VALID_PAYLOAD)
        as_json = model.model_dump_json()
        restored = ExperimentsSyncRequest.model_validate_json(as_json)
        assert restored == model


class TestExperimentsSyncRequestPublisher:

    def test_publisher_subclass_has_validator(self):
        assert ExperimentsSyncRequestPublisher.validator_class is ExperimentsSyncRequest

    def test_publish_sends_validated_json(self, monkeypatch):
        """Publisher.publish should validate the payload and route it through publish_message."""
        captured = {}

        def fake_publish_message(message, topic, **kwargs):
            captured["message"] = message
            captured["topic"] = topic

        # Patch the symbol inside the module that publish() actually calls
        import microdrop_utils.dramatiq_pub_sub_helpers as pub_sub
        monkeypatch.setattr(pub_sub, "publish_message", fake_publish_message)

        publisher = ExperimentsSyncRequestPublisher(topic="ssh_service/request/sync_experiments")
        publisher.publish(**VALID_PAYLOAD)

        assert captured["topic"] == "ssh_service/request/sync_experiments"
        # Message should be JSON decodable and contain all fields
        import json
        parsed = json.loads(captured["message"])
        assert parsed["host"] == VALID_PAYLOAD["host"]
        assert parsed["port"] == VALID_PAYLOAD["port"]
        assert parsed["identity_path"] == VALID_PAYLOAD["identity_path"]

    def test_publish_raises_on_invalid_payload(self):
        publisher = ExperimentsSyncRequestPublisher(topic="ssh_service/request/sync_experiments")
        with pytest.raises(ValidationError):
            publisher.publish(
                host="192.168.1.10",
                port="not-a-number",  # invalid
                username="u",
                identity_path="/p",
                src="s",
                dest="d",
            )
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
pytest examples/tests/test_ssh_controls_models.py -v
```

Expected: ImportError / ModuleNotFoundError for `ssh_controls.models`.

- [ ] **Step 3: Create `ssh_controls/models.py`**

```python
"""
Pydantic models and validated publishers for ssh_controls topics.

Follows the pattern from electrode_controller/models.py — each request
type is a Pydantic BaseModel paired with a ValidatedTopicPublisher
subclass that exposes a typed .publish(...) convenience method.
"""
from pydantic import BaseModel

from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher


class ExperimentsSyncRequest(BaseModel):
    """Payload for a remote experiments rsync-pull request.

    Attributes
    ----------
    host : str
        Hostname or IP address of the remote Microdrop backend.
    port : int
        SSH port on the remote host.
    username : str
        SSH username for the remote host.
    identity_path : str
        Absolute filesystem path to the SSH private key on the local
        (frontend) machine.
    src : str
        Remote source path, typically of the form
        ``"user@host:~/.../Experiments/"``. Trailing slash is significant —
        it tells rsync to copy directory *contents* rather than nest the
        directory inside the destination.
    dest : str
        Absolute local filesystem path where files will be written.
    """
    host: str
    port: int
    username: str
    identity_path: str
    src: str
    dest: str


class ExperimentsSyncRequestPublisher(ValidatedTopicPublisher):
    """Validated publisher for ``SYNC_EXPERIMENTS_REQUEST`` topic.

    Exposes a keyword-only .publish(...) method that mirrors the
    ExperimentsSyncRequest fields for call-site readability.
    """
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

- [ ] **Step 4: Run the tests again to confirm they pass**

```bash
pytest examples/tests/test_ssh_controls_models.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add ssh_controls/models.py examples/tests/test_ssh_controls_models.py
git commit -m "Add ExperimentsSyncRequest Pydantic model and publisher"
```

---

### Task 2: Add sync topics and publisher instance to `ssh_controls/consts.py`

**Files:**
- Modify: `ssh_controls/consts.py`

- [ ] **Step 1: Append the new topics and publisher to `ssh_controls/consts.py`**

After the existing `SSH_KEY_UPLOAD_ERROR` line, add:

```python
# --- Remote experiments sync ----------------------------------------------
# Request topic (frontend -> ssh_controls listener)
SYNC_EXPERIMENTS_REQUEST = "ssh_service/request/sync_experiments"

# Response topics (ssh_controls service -> frontend)
SYNC_EXPERIMENTS_STARTED = "ssh_service/started/sync_experiments"
SYNC_EXPERIMENTS_SUCCESS = "ssh_service/success/sync_experiments"
SYNC_EXPERIMENTS_ERROR   = "ssh_service/error/sync_experiments"
```

Then add `SYNC_EXPERIMENTS_REQUEST` to the existing `ACTOR_TOPIC_DICT` entry so it becomes:

```python
ACTOR_TOPIC_DICT = {
    listener_name: [
        GENERATE_KEYPAIR,
        KEY_UPLOAD,
        SYNC_EXPERIMENTS_REQUEST,
    ]
}
```

At the bottom of the file, add the module-level publisher singleton:

```python
# Convenience publisher singleton (matches electrode_controller/consts.py style).
# Imported here so call sites can do:
#   from ssh_controls.consts import experiments_sync_publisher
#   experiments_sync_publisher.publish(host=..., ...)
from ssh_controls.models import ExperimentsSyncRequestPublisher
experiments_sync_publisher = ExperimentsSyncRequestPublisher(topic=SYNC_EXPERIMENTS_REQUEST)
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
python -c "from ssh_controls.consts import experiments_sync_publisher, SYNC_EXPERIMENTS_REQUEST, SYNC_EXPERIMENTS_STARTED, SYNC_EXPERIMENTS_SUCCESS, SYNC_EXPERIMENTS_ERROR, ACTOR_TOPIC_DICT; print(SYNC_EXPERIMENTS_REQUEST, 'in dict:', SYNC_EXPERIMENTS_REQUEST in ACTOR_TOPIC_DICT['ssh_controls_listener'])"
```

Expected: `ssh_service/request/sync_experiments in dict: True`

- [ ] **Step 3: Commit**

```bash
git add ssh_controls/consts.py
git commit -m "Add sync_experiments topics and publisher to ssh_controls consts"
```

---

### Task 3: Add `_on_sync_experiments_request` handler to `SSHService`

**Files:**
- Modify: `ssh_controls/service.py`

- [ ] **Step 1: Add the new handler method to `SSHService`**

At the top of `ssh_controls/service.py`, add new imports:

```python
from microdrop_utils.file_sync_helpers import Rsync
from pydantic import ValidationError

from .consts import (
    listener_name, SSH_KEYGEN_SUCCESS,
    SSH_KEYGEN_WARNING, SSH_KEYGEN_ERROR,
    SSH_KEY_UPLOAD_ERROR, SSH_KEY_UPLOAD_SUCCESS,
    SYNC_EXPERIMENTS_STARTED, SYNC_EXPERIMENTS_SUCCESS, SYNC_EXPERIMENTS_ERROR,
)
from .models import ExperimentsSyncRequest
```

(Keep the existing imports that were already in the file; extend them rather than replacing.)

Then, inside the `SSHService` class, append a new handler method after `_on_key_upload_request`:

```python
def _on_sync_experiments_request(self, message):
    """Handler for ``ssh_service/request/sync_experiments``.

    Runs rsync over SSH as the local (frontend) host, pulling from
    the remote backend. Publishes a ``started`` ack on receipt and
    either ``success`` or ``error`` when the blocking rsync call
    completes. Blocks this dramatiq worker for the duration of the
    transfer (consistent with _on_key_upload_request).
    """
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

Note: the `basic_listener_actor_routine(self, message, topic, handler_name_pattern="_on_{topic}_request")` dispatch already in this class's `listener_actor_routine` will route topic `ssh_service/request/sync_experiments` to `_on_sync_experiments_request` automatically. No changes to the dispatch wiring are needed.

- [ ] **Step 2: Verify the module imports cleanly**

```bash
python -c "from ssh_controls.service import SSHService; print(hasattr(SSHService, '_on_sync_experiments_request'))"
```

Expected: `True`

- [ ] **Step 3: Commit**

```bash
git add ssh_controls/service.py
git commit -m "Handle sync_experiments request: rsync pull with started/success/error acks"
```

---

### Task 4: Integration test — backend handler round-trip with stubbed Rsync

**Files:**
- Create: `examples/tests/tests_with_redis_server_need/test_ssh_sync_experiments.py`

This test verifies the pub/sub round-trip against a real Redis. `Rsync` is stubbed so the test does not make any SSH calls.

- [ ] **Step 1: Write the failing integration test**

```python
"""
Integration test for the SYNC_EXPERIMENTS_REQUEST round-trip through
the ssh_controls service. Requires a running Redis server (see
examples/start_redis_server.py).

Rsync is stubbed; no SSH traffic is generated.
"""
import json
import subprocess
import threading
import time
from unittest.mock import patch

import pytest

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from ssh_controls.consts import (
    SYNC_EXPERIMENTS_REQUEST, SYNC_EXPERIMENTS_STARTED,
    SYNC_EXPERIMENTS_SUCCESS, SYNC_EXPERIMENTS_ERROR,
)


VALID_PAYLOAD = {
    "host": "test-host",
    "port": 22,
    "username": "user",
    "identity_path": "/tmp/fake-key",
    "src": "user@test-host:~/Experiments/",
    "dest": "/tmp/remote-experiments",
}


class _CollectedTopics:
    """Simple threadsafe collector for topics observed by a listener."""
    def __init__(self):
        self.topics = []
        self.lock = threading.Lock()

    def append(self, topic):
        with self.lock:
            self.topics.append(topic)


@pytest.fixture
def topic_collector(monkeypatch):
    """Patches publish_message inside ssh_controls.service to record published topics."""
    collector = _CollectedTopics()
    real_publish = publish_message

    def capture(message, topic, **kw):
        collector.append(topic)
        return real_publish(message, topic, **kw)

    import ssh_controls.service as svc
    monkeypatch.setattr(svc, "publish_message", capture)
    return collector


def _fake_rsync_ok(*args, **kwargs):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")


def _fake_rsync_fail(*args, **kwargs):
    return subprocess.CompletedProcess(args=[], returncode=23, stdout="", stderr="some error\n")


def _fake_rsync_missing(*args, **kwargs):
    raise FileNotFoundError("rsync not on PATH")


def test_happy_path_emits_started_then_success(topic_collector):
    """With rsync returning 0, handler should emit STARTED then SUCCESS."""
    import ssh_controls.service as svc
    from ssh_controls.service import SSHService

    # Build a real SSHService (which registers its listener actor at init)
    service = SSHService()

    # Stub Rsync().sync to return rc=0
    with patch.object(svc, "Rsync") as MockRsync:
        MockRsync.return_value.sync.side_effect = _fake_rsync_ok

        # Directly invoke the handler (synchronous path — no worker needed)
        service._on_sync_experiments_request(json.dumps(VALID_PAYLOAD))

    topics = topic_collector.topics
    assert SYNC_EXPERIMENTS_STARTED in topics
    assert SYNC_EXPERIMENTS_SUCCESS in topics
    assert topics.index(SYNC_EXPERIMENTS_STARTED) < topics.index(SYNC_EXPERIMENTS_SUCCESS)
    assert SYNC_EXPERIMENTS_ERROR not in topics


def test_nonzero_exit_emits_started_then_error(topic_collector):
    """rsync returning nonzero should produce STARTED then ERROR (no SUCCESS)."""
    import ssh_controls.service as svc
    from ssh_controls.service import SSHService

    service = SSHService()

    with patch.object(svc, "Rsync") as MockRsync:
        MockRsync.return_value.sync.side_effect = _fake_rsync_fail
        service._on_sync_experiments_request(json.dumps(VALID_PAYLOAD))

    topics = topic_collector.topics
    assert SYNC_EXPERIMENTS_STARTED in topics
    assert SYNC_EXPERIMENTS_ERROR in topics
    assert SYNC_EXPERIMENTS_SUCCESS not in topics


def test_rsync_missing_emits_started_then_error(topic_collector):
    """FileNotFoundError from Rsync should produce STARTED then ERROR."""
    import ssh_controls.service as svc
    from ssh_controls.service import SSHService

    service = SSHService()

    with patch.object(svc, "Rsync") as MockRsync:
        MockRsync.return_value.sync.side_effect = _fake_rsync_missing
        service._on_sync_experiments_request(json.dumps(VALID_PAYLOAD))

    topics = topic_collector.topics
    assert SYNC_EXPERIMENTS_STARTED in topics
    assert SYNC_EXPERIMENTS_ERROR in topics


def test_invalid_payload_emits_error_only(topic_collector):
    """Invalid JSON payload should emit ERROR only (no STARTED)."""
    from ssh_controls.service import SSHService

    service = SSHService()
    # Missing 'dest'
    bad = dict(VALID_PAYLOAD)
    del bad["dest"]

    service._on_sync_experiments_request(json.dumps(bad))

    topics = topic_collector.topics
    assert SYNC_EXPERIMENTS_ERROR in topics
    assert SYNC_EXPERIMENTS_STARTED not in topics
    assert SYNC_EXPERIMENTS_SUCCESS not in topics
```

- [ ] **Step 2: Run the tests to confirm they pass**

Prerequisites: Redis server running (user starts this separately if needed).

```bash
pytest examples/tests/tests_with_redis_server_need/test_ssh_sync_experiments.py -v
```

Expected: all four tests pass.

- [ ] **Step 3: Commit**

```bash
git add examples/tests/tests_with_redis_server_need/test_ssh_sync_experiments.py
git commit -m "Integration tests: sync_experiments handler started/success/error paths"
```

---

## Frontend — `ssh_controls_ui/sync_dialog/` subpackage

### Task 5: Create sync-dialog package skeleton + `model.py`

**Files:**
- Create: `ssh_controls_ui/sync_dialog/__init__.py`
- Create: `ssh_controls_ui/sync_dialog/model.py`

- [ ] **Step 1: Create `ssh_controls_ui/sync_dialog/__init__.py`** (empty file)

```python
```

- [ ] **Step 2: Create `ssh_controls_ui/sync_dialog/model.py`**

```python
"""Traits model for the Sync Remote Experiments dialog.

Holds field values edited by the user and the transient run state
(status text, in_progress flag). Pre-populates host/port/username
from the same .env variables used by SSHControlModel so the two
dialogs start in sync.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from traits.api import HasTraits, Str, Int, Bool
from traits.etsconfig.api import ETSConfig

load_dotenv()


class SyncDialogModel(HasTraits):
    """State of the Sync Remote Experiments dialog."""
    host = Str(os.getenv("REMOTE_HOST_IP_ADDRESS", ""))
    port = Int(int(os.getenv("REMOTE_SSH_PORT") or 22))
    username = Str(os.getenv("REMOTE_HOST_USERNAME", ""))

    # Identity file lives in ~/.ssh/<key_name> on the local host
    key_name = Str("id_rsa_microdrop")

    # Remote path to pull from (trailing slash ⇒ copy contents, not the dir)
    remote_experiments_path = Str("~/Documents/Sci-Bots/Microdrop/Experiments/")

    # Dialog run state
    status = Str("Idle")
    in_progress = Bool(False)

    def _default_dest(self) -> str:
        """Resolve the default local destination path."""
        return str(Path(ETSConfig.user_data) / "Remote-Experiments")

    def resolve_identity_path(self) -> str:
        return str(Path.home() / ".ssh" / self.key_name)

    def resolve_src(self) -> str:
        """Build ``user@host:path`` form expected by rsync."""
        return f"{self.username}@{self.host}:{self.remote_experiments_path}"
```

- [ ] **Step 3: Verify imports**

```bash
python -c "from ssh_controls_ui.sync_dialog.model import SyncDialogModel; m = SyncDialogModel(); print(m.resolve_identity_path(), '|', m._default_dest())"
```

Expected: two non-empty paths separated by `|`.

- [ ] **Step 4: Commit**

```bash
git add ssh_controls_ui/sync_dialog/__init__.py ssh_controls_ui/sync_dialog/model.py
git commit -m "Add SyncDialogModel with .env-derived defaults and path resolvers"
```

---

### Task 6: Add sync-listener name + response topic routes to `ssh_controls_ui/consts.py`

**Files:**
- Modify: `ssh_controls_ui/consts.py`

- [ ] **Step 1: Extend the module with the sync listener name and the three response topics**

Replace the current contents of `ssh_controls_ui/consts.py` with:

```python
# This module's package.
import os

from ssh_controls.consts import (
    SSH_KEYGEN_SUCCESS, SSH_KEYGEN_WARNING, SSH_KEYGEN_ERROR,
    SSH_KEY_UPLOAD_SUCCESS, SSH_KEY_UPLOAD_ERROR,
    SYNC_EXPERIMENTS_STARTED, SYNC_EXPERIMENTS_SUCCESS, SYNC_EXPERIMENTS_ERROR,
)

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

HELP_PATH = os.path.join(os.path.dirname(__file__), "help")

# Listener for the SSH Key Portal dialog
listener_name = f"{PKG}_listener"

# Listener for the Sync Remote Experiments dialog (separate so each dialog
# owns its own topic set)
sync_listener_name = f"{PKG}_sync_listener"

ACTOR_TOPIC_DICT = {
    listener_name: [
        SSH_KEYGEN_SUCCESS,
        SSH_KEYGEN_WARNING,
        SSH_KEYGEN_ERROR,
        SSH_KEY_UPLOAD_SUCCESS,
        SSH_KEY_UPLOAD_ERROR,
    ],
    sync_listener_name: [
        SYNC_EXPERIMENTS_STARTED,
        SYNC_EXPERIMENTS_SUCCESS,
        SYNC_EXPERIMENTS_ERROR,
    ],
}
```

- [ ] **Step 2: Verify imports**

```bash
python -c "from ssh_controls_ui.consts import ACTOR_TOPIC_DICT, sync_listener_name; print(sync_listener_name, list(ACTOR_TOPIC_DICT.keys()))"
```

Expected: prints `ssh_controls_ui_sync_listener` and both keys.

- [ ] **Step 3: Commit**

```bash
git add ssh_controls_ui/consts.py
git commit -m "Add sync_listener_name and sync response topics to ssh_controls_ui consts"
```

---

### Task 7: Create `sync_dialog/view_model.py`

**Files:**
- Create: `ssh_controls_ui/sync_dialog/view_model.py`

- [ ] **Step 1: Write `view_model.py`**

```python
"""ViewModel for the Sync Remote Experiments dialog.

Mediates between the Qt View (widget.py) and the Dramatiq response
listener. Responsible for:
  - validating pre-publish conditions (identity file exists, fields
    non-empty),
  - publishing the sync request via the typed publisher,
  - managing a 60s timeout QTimer that surfaces a "Keep Waiting / Quit"
    prompt to the user,
  - dispatching Dramatiq-delivered ``started`` / ``success`` / ``error``
    topics onto Qt signals the View binds to.
"""
import json
import os
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from pydantic import ValidationError
from traits.api import HasTraits, Instance, Str

from logger.logger_service import get_logger
from ssh_controls.consts import experiments_sync_publisher
from .model import SyncDialogModel

logger = get_logger(__name__)

# Timeout (ms) before showing the "Keep Waiting / Quit" prompt.
TIMEOUT_MS = 60_000


class SyncDialogViewModelSignals(QObject):
    """Qt signals the View binds to for UI updates."""
    status_changed      = Signal(str)
    enable_sync_button  = Signal(bool)
    show_in_progress    = Signal(bool)          # spinner visibility
    show_timeout_warning = Signal()             # triggers Keep-Waiting/Quit dialog
    show_message_box    = Signal(str, str, str) # msg_type, title, text
    close_dialog        = Signal()


class SyncDialogViewModel(HasTraits):
    """ViewModel for the Sync Remote Experiments dialog."""
    model = Instance(SyncDialogModel)
    view_signals = Instance(SyncDialogViewModelSignals)
    name = Str("Sync Dialog View Model")

    # Non-trait attribute — assigned in traits_init. Not a Trait because
    # QTimer is owned by Qt and we want to tie it to the Qt event loop.
    _timeout_timer = None

    def traits_init(self):
        self._timeout_timer = QTimer()
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.setInterval(TIMEOUT_MS)
        self._timeout_timer.timeout.connect(self._on_timeout_fired)

    # ---- View → ViewModel (commands) ------------------------------------
    @Slot()
    def sync_command(self):
        """Called when the user clicks the Sync button."""
        # Validate fields up-front to keep error cases UI-local.
        if not all([self.model.host, self.model.username, self.model.port]):
            self.view_signals.show_message_box.emit(
                "error", "Missing fields",
                "Host, username and port are required."
            )
            return

        identity_path = self.model.resolve_identity_path()
        if not Path(identity_path).exists():
            self.view_signals.show_message_box.emit(
                "error", "SSH key missing",
                f"Expected {identity_path} to exist. "
                "Generate + upload it via the SSH Key Portal first."
            )
            return

        # Resolve destination and ensure parent exists.
        dest = self.model._default_dest()
        os.makedirs(dest, exist_ok=True)

        src = self.model.resolve_src()

        self.model.in_progress = True
        self.view_signals.enable_sync_button.emit(False)
        self.view_signals.show_in_progress.emit(True)
        self.view_signals.status_changed.emit(
            "Request sent, waiting for backend..."
        )

        try:
            experiments_sync_publisher.publish(
                host=self.model.host,
                port=int(self.model.port),
                username=self.model.username,
                identity_path=identity_path,
                src=src,
                dest=dest,
            )
        except ValidationError as e:
            self._reset_ui_state()
            self.view_signals.show_message_box.emit(
                "error", "Invalid sync request", str(e),
            )
            return

        self._timeout_timer.start()

    @Slot()
    def quit_command(self):
        """Frontend-only dismiss — backend rsync keeps running (v1 behavior)."""
        self._timeout_timer.stop()
        self.model.in_progress = False
        self.view_signals.close_dialog.emit()

    @Slot()
    def keep_waiting_command(self):
        """User chose to keep waiting after the timeout warning."""
        self._timeout_timer.start()  # restart another TIMEOUT_MS window
        self.view_signals.status_changed.emit(
            "Still syncing..."
        )

    # ---- Data binding slots ---------------------------------------------
    @Slot(str)
    def set_host(self, text):
        self.model.host = text

    @Slot(str)
    def set_port_str(self, text):
        try:
            self.model.port = int(text)
        except ValueError:
            if not text:
                self.model.port = 0

    @Slot(str)
    def set_username(self, text):
        self.model.username = text

    @Slot(str)
    def set_key_name(self, text):
        self.model.key_name = text.strip()

    @Slot(str)
    def set_remote_path(self, text):
        self.model.remote_experiments_path = text

    # ---- Dramatiq-triggered handlers ------------------------------------
    def _on_sync_experiments_started_triggered(self, message):
        if not self.model.in_progress:
            logger.info("sync started received after quit; ignoring")
            return
        # Reset timeout — backend is alive
        self._timeout_timer.start()
        self.view_signals.status_changed.emit("Backend acknowledged, syncing...")

    def _on_sync_experiments_success_triggered(self, message):
        if not self.model.in_progress:
            logger.info("sync success received after quit; logged only: %s", message)
            return
        self._timeout_timer.stop()
        try:
            payload = json.loads(message)
            text = payload.get("message", "Sync complete.")
        except Exception:
            text = "Sync complete."
        self._reset_ui_state()
        self.view_signals.show_message_box.emit("info", "Sync complete", text)
        self.view_signals.close_dialog.emit()

    def _on_sync_experiments_error_triggered(self, message):
        if not self.model.in_progress:
            logger.error("sync error received after quit; logged only: %s", message)
            return
        self._timeout_timer.stop()
        try:
            payload = json.loads(message)
            title = payload.get("title", "Sync failed")
            text = payload.get("text", message)
        except Exception:
            title, text = "Sync failed", message
        self._reset_ui_state()
        self.view_signals.show_message_box.emit("error", title, text)

    # ---- Internal helpers ------------------------------------------------
    def _on_timeout_fired(self):
        self.view_signals.show_timeout_warning.emit()

    def _reset_ui_state(self):
        self.model.in_progress = False
        self.view_signals.show_in_progress.emit(False)
        self.view_signals.enable_sync_button.emit(True)
```

- [ ] **Step 2: Verify imports**

```bash
python -c "from ssh_controls_ui.sync_dialog.view_model import SyncDialogViewModel, SyncDialogViewModelSignals; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add ssh_controls_ui/sync_dialog/view_model.py
git commit -m "Add SyncDialogViewModel with timeout timer and Dramatiq handlers"
```

---

### Task 8: Create `sync_dialog/dramatiq_listener.py`

**Files:**
- Create: `ssh_controls_ui/sync_dialog/dramatiq_listener.py`

- [ ] **Step 1: Write the listener**

```python
"""Dramatiq listener bridging sync response topics onto SyncDialogViewModel."""
import dramatiq
from traits.api import HasTraits, provides, Instance

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_controller_base import (
    IDramatiqControllerBase,
    basic_listener_actor_routine,
    generate_class_method_dramatiq_listener_actor,
)

from .view_model import SyncDialogViewModel
from ..consts import sync_listener_name

logger = get_logger(__name__)


@provides(IDramatiqControllerBase)
class SyncDialogListener(HasTraits):
    """Separate listener so each dialog owns its own topic set.

    The SSH Key Portal dialog uses SSHControlUIListener; this listener is
    dedicated to the three SYNC_EXPERIMENTS_* response topics and
    dispatches them to `_on_{sub_topic}_triggered` methods on the
    SyncDialogViewModel using the standard basic_listener_actor_routine
    convention.
    """
    ui = Instance(SyncDialogViewModel)

    dramatiq_listener_actor = Instance(dramatiq.Actor)
    name = sync_listener_name

    def traits_init(self):
        logger.info("Starting sync dialog dramatiq listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=sync_listener_name,
            class_method=self.listener_actor_routine,
        )

    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(self.ui, message, topic)
```

- [ ] **Step 2: Verify imports**

```bash
python -c "from ssh_controls_ui.sync_dialog.dramatiq_listener import SyncDialogListener; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add ssh_controls_ui/sync_dialog/dramatiq_listener.py
git commit -m "Add SyncDialogListener dispatching sync topics to ViewModel handlers"
```

---

### Task 9: Create `sync_dialog/widget.py`

**Files:**
- Create: `ssh_controls_ui/sync_dialog/widget.py`

- [ ] **Step 1: Write the widget**

```python
"""Qt widget for the Sync Remote Experiments dialog."""
from PySide6.QtCore import Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QFormLayout,
    QLineEdit, QPushButton, QLabel, QProgressBar, QMessageBox,
)


class SyncDialogView(QWidget):
    """Qt View for the Sync Remote Experiments dialog."""

    def __init__(self, view_model, parent=None):
        super().__init__(parent)
        self.view_model = view_model

        layout = QVBoxLayout(self)

        # --- Connection fields ---
        conn_group = QGroupBox("1. Remote Host")
        conn_layout = QFormLayout()
        self.host_entry = QLineEdit()
        self.port_entry = QLineEdit()
        self.user_entry = QLineEdit()
        self.key_name_entry = QLineEdit()
        conn_layout.addRow("Host:", self.host_entry)
        conn_layout.addRow("Port:", self.port_entry)
        conn_layout.addRow("Username:", self.user_entry)
        conn_layout.addRow("Key Name:", self.key_name_entry)
        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)

        # --- Paths ---
        paths_group = QGroupBox("2. Paths")
        paths_layout = QFormLayout()
        self.remote_path_entry = QLineEdit()
        self.local_dest_label = QLabel()
        self.local_dest_label.setWordWrap(True)
        paths_layout.addRow("Remote source:", self.remote_path_entry)
        paths_layout.addRow("Local destination:", self.local_dest_label)
        paths_group.setLayout(paths_layout)
        layout.addWidget(paths_group)

        # --- Sync action ---
        action_group = QGroupBox("3. Sync")
        action_layout = QVBoxLayout()
        self.sync_button = QPushButton("Sync Remote Experiments")
        self.sync_button.setMinimumHeight(40)
        action_layout.addWidget(self.sync_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # indeterminate
        self.progress_bar.setVisible(False)
        action_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Status: Idle")
        self.status_label.setWordWrap(True)
        action_layout.addWidget(self.status_label)

        action_group.setLayout(action_layout)
        layout.addWidget(action_group)
        layout.addStretch()

    def initialize_field_values(self, host="", port=22, username="",
                                key_name="", remote_path="",
                                local_dest=""):
        self.host_entry.setText(host)
        self.port_entry.setText(str(port))
        self.user_entry.setText(username)
        self.key_name_entry.setText(key_name)
        self.remote_path_entry.setText(remote_path)
        self.local_dest_label.setText(local_dest)

    def connect_signals(self):
        vm = self.view_model
        s = vm.view_signals

        # View -> ViewModel (bindings)
        self.host_entry.textChanged.connect(vm.set_host)
        self.port_entry.textChanged.connect(vm.set_port_str)
        self.user_entry.textChanged.connect(vm.set_username)
        self.key_name_entry.textChanged.connect(vm.set_key_name)
        self.remote_path_entry.textChanged.connect(vm.set_remote_path)

        # View -> ViewModel (commands)
        self.sync_button.clicked.connect(vm.sync_command)

        # ViewModel -> View (UI updates)
        s.status_changed.connect(lambda text: self.status_label.setText(f"Status: {text}"))
        s.enable_sync_button.connect(self.sync_button.setEnabled)
        s.show_in_progress.connect(self.progress_bar.setVisible)
        s.show_message_box.connect(self.show_message_box)
        s.show_timeout_warning.connect(self.show_timeout_warning)
        s.close_dialog.connect(self._close_parent_window)

    @Slot(str, str, str)
    def show_message_box(self, msg_type, title, text):
        if msg_type == "error":
            QMessageBox.critical(self, title, text)
        elif msg_type == "info":
            QMessageBox.information(self, title, text)
        else:
            QMessageBox.warning(self, title, text)

    @Slot()
    def show_timeout_warning(self):
        """Prompt the user when the sync takes longer than expected."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Still syncing")
        box.setText(
            "The remote sync is taking longer than expected. "
            "Keep waiting, or quit and let it finish in the background?"
        )
        keep_btn = box.addButton("Keep Waiting", QMessageBox.AcceptRole)
        quit_btn = box.addButton("Quit", QMessageBox.RejectRole)
        box.exec()

        if box.clickedButton() is keep_btn:
            self.view_model.keep_waiting_command()
        else:
            self.view_model.quit_command()

    @Slot()
    def _close_parent_window(self):
        """Close the containing QMainWindow when the ViewModel asks to."""
        window = self.window()
        if window is not None:
            window.close()
```

- [ ] **Step 2: Verify imports**

```bash
python -c "from ssh_controls_ui.sync_dialog.widget import SyncDialogView; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add ssh_controls_ui/sync_dialog/widget.py
git commit -m "Add SyncDialogView widget with spinner, status label, and timeout prompt"
```

---

### Task 10: Wire the menu action in `ssh_controls_ui/menus.py`

**Files:**
- Modify: `ssh_controls_ui/menus.py`

- [ ] **Step 1: Add the new window class, action, and update `menu_factory`**

Replace the current `ssh_controls_ui/menus.py` with:

```python
from PySide6.QtWidgets import QMainWindow
from pyface.action.api import Action
from pyface.tasks.action.api import SGroup

from .dramatiq_listener import SSHControlUIListener
from .view_model import SSHControlViewModel, SSHControlViewModelSignals
from .widget import SSHControlView
from .model import SSHControlModel

from .sync_dialog.dramatiq_listener import SyncDialogListener
from .sync_dialog.model import SyncDialogModel
from .sync_dialog.view_model import SyncDialogViewModel, SyncDialogViewModelSignals
from .sync_dialog.widget import SyncDialogView


class SshKeyUploaderApp(QMainWindow):
    """Main window for the SSH Key Portal dialog."""

    def __init__(self, main_widget):
        super().__init__()
        self.setWindowTitle("SSH Key Portal")
        self.setGeometry(100, 100, 480, 500)
        self.setCentralWidget(main_widget)


class ShowSshKeyUploaderAction(Action):
    """Pyface action that shows the SSH Key Portal window."""
    name = "SSH &Key Portal..."
    accelerator = "Ctrl+Shift+S"
    tooltip = "Launch the SSH Key Uploader application."
    style = "window"

    def traits_init(self, *args, **kwargs):
        self._window = None
        self.model = SSHControlModel()
        self.view_model = SSHControlViewModel(
            model=self.model,
            view_signals=SSHControlViewModelSignals(),
        )
        self.listener = SSHControlUIListener(ui=self.view_model)

    def perform(self, event):
        if self._window is not None:
            self._window.close()
            self._window = None

        widget = SSHControlView(view_model=self.view_model)
        widget.initialize_field_values(
            host=self.model.host,
            port=self.model.port,
            username=self.model.username,
            password=self.model.password,
            key_name=self.model.key_name,
        )
        widget.connect_signals()

        self._window = SshKeyUploaderApp(main_widget=widget)
        self._window.show()


class SyncDialogApp(QMainWindow):
    """Main window for the Sync Remote Experiments dialog."""

    def __init__(self, main_widget):
        super().__init__()
        self.setWindowTitle("Sync Remote Experiments")
        self.setGeometry(150, 150, 480, 360)
        self.setCentralWidget(main_widget)


class ShowSyncRemoteExperimentsAction(Action):
    """Pyface action that shows the Sync Remote Experiments dialog."""
    name = "Sync Remote &Experiments..."
    tooltip = "Pull the remote backend's Experiments/ folder locally via rsync over SSH."
    style = "window"

    def traits_init(self, *args, **kwargs):
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
            self._window = None

        widget = SyncDialogView(view_model=self.view_model)
        widget.initialize_field_values(
            host=self.model.host,
            port=self.model.port,
            username=self.model.username,
            key_name=self.model.key_name,
            remote_path=self.model.remote_experiments_path,
            local_dest=self.model._default_dest(),
        )
        widget.connect_signals()

        self._window = SyncDialogApp(main_widget=widget)
        self._window.show()


def menu_factory():
    """Menu group containing both SSH actions."""
    return SGroup(
        ShowSshKeyUploaderAction(),
        ShowSyncRemoteExperimentsAction(),
        id="remote_controls",
    )
```

- [ ] **Step 2: Verify imports**

```bash
python -c "from ssh_controls_ui.menus import menu_factory; print(menu_factory())"
```

Expected: prints an `SGroup` object, no errors.

- [ ] **Step 3: Commit**

```bash
git add ssh_controls_ui/menus.py
git commit -m "Wire ShowSyncRemoteExperimentsAction into ssh_controls_ui menu"
```

---

## Plugin registration — `examples/plugin_consts.py`

### Task 11: Introduce `SERVICE_PLUGINS`, register the SSH plugins, drop the scaffold import

**Files:**
- Modify: `examples/plugin_consts.py`

- [ ] **Step 1: Update the plugin-consts module**

Replace the current contents of `examples/plugin_consts.py` with:

```python
import os

from dropbot_preferences_ui.plugin import DropbotPreferencesPlugin
from dropbot_status_and_controls.plugin import DropbotStatusAndControlsPlugin
from logger.plugin import LoggerPlugin
from logger_ui.plugin import LoggerUIPlugin
from manual_controls.plugin import ManualControlsPlugin
from microdrop_application.application import MicrodropApplication
from microdrop_application.backend_application import MicrodropBackendApplication
from microdrop_application.plugin import MicrodropPlugin
from dropbot_tools_menu.plugin import DropbotToolsMenuPlugin
from opendrop_status_and_controls.plugin import OpendropStatusAndControlsPlugin
from peripheral_controller.plugin import PeripheralControllerPlugin
from protocol_grid.plugin import ProtocolGridControllerUIPlugin
from dropbot_controller.plugin import DropbotControllerPlugin
from electrode_controller.plugin import ElectrodeControllerPlugin
from envisage.api import CorePlugin
from envisage.ui.tasks.api import TasksPlugin
from message_router.plugin import MessageRouterPlugin
from microdrop_utils.broker_server_helpers import dramatiq_workers_context, redis_server_context
from device_viewer.plugin import DeviceViewerPlugin
from peripherals_ui.plugin import PeripheralUiPlugin
from opendrop_controller.plugin import OpenDropControllerPlugin
from mock_dropbot_controller.plugin import MockDropbotControllerPlugin
from mock_dropbot_status.plugin import MockDropbotStatusPlugin
from ssh_controls.plugin import SSHControlsPlugin
from ssh_controls_ui.plugin import SSHUIPlugin
from user_help_plugin.plugin import UserHelpPlugin

# The order of plugins matters. This determines whose start routine will be run first,
# and whose contributions will be prioritized
# For example: the microdrop plugin and the tasks contributes a preferences dialog service.
# The dialog contributed by the plugin listed first will be used. That is how the envisage application get_service
# method works.

# ---------------------------------------------------------------------------
# Plugin categories
# ---------------------------------------------------------------------------
# There are three categories:
#
#   FRONTEND_PLUGINS — Qt/Pyface UI plugins. Must run in the GUI process.
#   BACKEND_PLUGINS  — Plugins that talk to physical hardware (DropBot,
#                      OpenDrop, peripherals). Must run on the host wired
#                      to the device.
#   SERVICE_PLUGINS  — Dramatiq-worker plugins that are host-bound by
#                      user-trust context (credentials, private keys,
#                      local filesystem), not by hardware or UI. These
#                      must colocate with the GUI process, not with the
#                      remote backend.
#
# A service plugin (e.g., ssh_controls) has no UI and no hardware
# dependency — but shipping it to the remote backend host would either
# fail (no SSH keys there) or invert the rsync direction and force the
# backend to push files into the frontend, which we explicitly reject.
# Keep service plugins in this list and include it in the plugin sets
# for any run script that launches the GUI.
# ---------------------------------------------------------------------------

FRONTEND_PLUGINS = [
    MicrodropPlugin,
    TasksPlugin,
    LoggerUIPlugin,
    ProtocolGridControllerUIPlugin,
    DeviceViewerPlugin,
    PeripheralUiPlugin,
    UserHelpPlugin,
    SSHUIPlugin,
]

DROPBOT_FRONTEND_PLUGINS = [
    DropbotPreferencesPlugin,
    DropbotStatusAndControlsPlugin,
    DropbotToolsMenuPlugin,
]

OPENDROP_FRONTEND_PLUGINS = [
    OpendropStatusAndControlsPlugin
]


BACKEND_PLUGINS = [
    ElectrodeControllerPlugin,
]

OPENDROP_BACKEND_PLUGINS = [
    OpenDropControllerPlugin,
]

DROPBOT_BACKEND_PLUGINS = [
    PeripheralControllerPlugin,
    DropbotControllerPlugin
]

# Mock DropBot plugins — swap these in place of DROPBOT_BACKEND_PLUGINS
# and DROPBOT_FRONTEND_PLUGINS to use the mock controller (no hardware needed).
MOCK_DROPBOT_BACKEND_PLUGINS = [
    MockDropbotControllerPlugin,
]

MOCK_DROPBOT_FRONTEND_PLUGINS = [
    MockDropbotStatusPlugin,
]

# Host-bound-by-trust plugins. See the category comment above.
SERVICE_PLUGINS = [
    SSHControlsPlugin,
]

REQUIRED_PLUGINS = [
    CorePlugin,
    MessageRouterPlugin,
    LoggerPlugin
]

REQUIRED_CONTEXT = [
    (dramatiq_workers_context, {"worker_threads": 4, "worker_timeout": 100}) #TODO optimize threads and timeout
]

SERVER_CONTEXT = [
    (redis_server_context, {})
]

BACKEND_APPLICATION = MicrodropBackendApplication

FRONTEND_APPLICATION = MicrodropApplication

DEFAULT_APPLICATION = MicrodropApplication
```

- [ ] **Step 2: Verify imports**

```bash
python -c "from examples.plugin_consts import SERVICE_PLUGINS, FRONTEND_PLUGINS; print([p.__name__ for p in SERVICE_PLUGINS], 'SSHUI in FE:', any(p.__name__=='SSHUIPlugin' for p in FRONTEND_PLUGINS))"
```

Expected: `['SSHControlsPlugin'] SSHUI in FE: True`

- [ ] **Step 3: Commit**

```bash
git add examples/plugin_consts.py
git commit -m "Introduce SERVICE_PLUGINS category; register SSHControls and SSHUI plugins"
```

---

### Task 12: Include `SERVICE_PLUGINS` in the GUI run scripts

**Files:**
- Modify: `examples/run_device_viewer_pluggable.py`
- Modify: `examples/run_device_viewer_pluggable_frontend.py`

Only the two GUI-hosting run scripts get `SERVICE_PLUGINS`. The backend-only script (`run_device_viewer_pluggable_backend.py`) intentionally does not — service plugins must colocate with the GUI.

- [ ] **Step 1: Update `examples/run_device_viewer_pluggable.py`**

Change the import block at line 14-16 to include `SERVICE_PLUGINS`:

```python
from examples.plugin_consts import REQUIRED_PLUGINS, FRONTEND_PLUGINS, BACKEND_PLUGINS, DROPBOT_BACKEND_PLUGINS, \
    DROPBOT_FRONTEND_PLUGINS, OPENDROP_FRONTEND_PLUGINS, OPENDROP_BACKEND_PLUGINS, DEFAULT_APPLICATION, SERVER_CONTEXT, \
    REQUIRED_CONTEXT, MOCK_DROPBOT_BACKEND_PLUGINS, MOCK_DROPBOT_FRONTEND_PLUGINS, SERVICE_PLUGINS
```

And update the plugin aggregation line (was line 94):

```python
    plugins = REQUIRED_PLUGINS + FRONTEND_PLUGINS + SERVICE_PLUGINS + BACKEND_PLUGINS
```

- [ ] **Step 2: Update `examples/run_device_viewer_pluggable_frontend.py`**

Change the import line 5-6 to include `SERVICE_PLUGINS`:

```python
from examples.plugin_consts import REQUIRED_PLUGINS, FRONTEND_PLUGINS, REQUIRED_CONTEXT, FRONTEND_APPLICATION, \
    DROPBOT_FRONTEND_PLUGINS, OPENDROP_FRONTEND_PLUGINS, SERVICE_PLUGINS
```

And update the `plugins = ...` line in `main`:

```python
    plugins = REQUIRED_PLUGINS + FRONTEND_PLUGINS + SERVICE_PLUGINS
```

- [ ] **Step 3: Verify imports**

```bash
python -c "import ast; ast.parse(open('examples/run_device_viewer_pluggable.py').read()); ast.parse(open('examples/run_device_viewer_pluggable_frontend.py').read()); print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add examples/run_device_viewer_pluggable.py examples/run_device_viewer_pluggable_frontend.py
git commit -m "Include SERVICE_PLUGINS in frontend and full-app run scripts"
```

---

## API surface — `microdrop_utils/api.py`

### Task 13: Add the three new topics to `SSHTopics`

**Files:**
- Modify: `microdrop_utils/api.py`

- [ ] **Step 1: Extend `SSHTopics`**

Inside the existing `SSHTopics` class, add a new `Requests.SYNC_EXPERIMENTS`, a new `Started` nested class, and entries under `Success` and `Errors`:

```python
class SSHTopics:
    """Topics for the SSH key management service."""

    class Requests:
        """Requests accepted by the SSH controls backend."""
        GENERATE_KEYPAIR            = _ssh.GENERATE_KEYPAIR
        KEY_UPLOAD                  = _ssh.KEY_UPLOAD
        SYNC_EXPERIMENTS            = _ssh.SYNC_EXPERIMENTS_REQUEST

    class Started:
        """Progress signals published by the SSH controls service."""
        SYNC_EXPERIMENTS_STARTED    = _ssh.SYNC_EXPERIMENTS_STARTED

    class Success:
        """Success signals published by the SSH controls backend."""
        SSH_KEYGEN_SUCCESS          = _ssh.SSH_KEYGEN_SUCCESS
        SSH_KEY_UPLOAD_SUCCESS      = _ssh.SSH_KEY_UPLOAD_SUCCESS
        SYNC_EXPERIMENTS_SUCCESS    = _ssh.SYNC_EXPERIMENTS_SUCCESS

    class Warnings:
        """Warning signals published by the SSH controls backend."""
        SSH_KEYGEN_WARNING          = _ssh.SSH_KEYGEN_WARNING

    class Errors:
        """Error signals published by the SSH controls backend."""
        SSH_KEYGEN_ERROR            = _ssh.SSH_KEYGEN_ERROR
        SSH_KEY_UPLOAD_ERROR        = _ssh.SSH_KEY_UPLOAD_ERROR
        SYNC_EXPERIMENTS_ERROR      = _ssh.SYNC_EXPERIMENTS_ERROR
```

Make sure `_ssh` (the alias used by the surrounding file for `ssh_controls.consts`) is the one already imported — do **not** add a new import alias. Read the top of `api.py` to confirm the alias name before editing.

- [ ] **Step 2: Verify imports**

```bash
python -c "from microdrop_utils.api import SSHTopics; print(SSHTopics.Requests.SYNC_EXPERIMENTS, SSHTopics.Success.SYNC_EXPERIMENTS_SUCCESS, SSHTopics.Started.SYNC_EXPERIMENTS_STARTED, SSHTopics.Errors.SYNC_EXPERIMENTS_ERROR)"
```

Expected: four `ssh_service/...` topic strings printed.

- [ ] **Step 3: Commit**

```bash
git add microdrop_utils/api.py
git commit -m "Expose SYNC_EXPERIMENTS_* topics through SSHTopics API"
```

---

### Task 14: Extend `TestSSHTopicsMatchConsts` for the new topics

**Files:**
- Modify: `examples/tests/test_messaging_api.py`

- [ ] **Step 1: Add the assertions**

Inside `TestSSHTopicsMatchConsts`, add three new test methods after the existing ones:

```python
    def test_sync_experiments_request(self):
        from ssh_controls.consts import SYNC_EXPERIMENTS_REQUEST
        assert SSHTopics.Requests.SYNC_EXPERIMENTS == SYNC_EXPERIMENTS_REQUEST

    def test_sync_experiments_started(self):
        from ssh_controls.consts import SYNC_EXPERIMENTS_STARTED
        assert SSHTopics.Started.SYNC_EXPERIMENTS_STARTED == SYNC_EXPERIMENTS_STARTED

    def test_sync_experiments_success_and_error(self):
        from ssh_controls.consts import SYNC_EXPERIMENTS_SUCCESS, SYNC_EXPERIMENTS_ERROR
        assert SSHTopics.Success.SYNC_EXPERIMENTS_SUCCESS == SYNC_EXPERIMENTS_SUCCESS
        assert SSHTopics.Errors.SYNC_EXPERIMENTS_ERROR == SYNC_EXPERIMENTS_ERROR
```

- [ ] **Step 2: Run the tests**

```bash
pytest examples/tests/test_messaging_api.py::TestSSHTopicsMatchConsts -v
```

Expected: all tests in the class (original + three new ones) pass.

- [ ] **Step 3: Commit**

```bash
git add examples/tests/test_messaging_api.py
git commit -m "Test: SSHTopics API exposes sync_experiments request/started/success/error"
```

---

## Manual verification

### Task 15: Smoke test via the full application run script

Run the full application with a mock DropBot so no hardware is required. Verify that:

1. The app launches without import errors.
2. Menu `Edit → Sync Remote &Experiments...` appears.
3. Clicking it opens the Sync dialog pre-populated from `.env`.
4. Clicking Sync with no key configured produces an "SSH key missing" error box (not a crash).
5. Clicking Sync with a valid key produces the "Request sent..." then "Backend acknowledged, syncing..." status transitions and either a success info box or an error box depending on the remote availability.

**Files:** none modified

- [ ] **Step 1: Start Redis**

```bash
python examples/start_redis_server.py
```

- [ ] **Step 2: Run the full app with mock device in another terminal**

```bash
python examples/run_device_viewer_pluggable.py --device mock
```

- [ ] **Step 3: Verify the flow above**

Record any deviations as issues in the existing GitHub issue tracker per project convention (https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/).

- [ ] **Step 4: No commit — manual verification only**

---

## Final task

### Task 16: Push the branch

**Files:** none

- [ ] **Step 1: Push the branch**

```bash
git push -u origin feat/remote-experiments-sync --force-with-lease
```

`--force-with-lease` is required because Task 0 rewrote history. It refuses to push if the remote has advanced since the last fetch (safer than plain `--force`).

- [ ] **Step 2: Open the PR**

Done via `gh pr create` or the project's standard workflow. The PR title should reference the SERVICE_PLUGINS addition as a meaningful side effect alongside the sync feature.

---

## Glossary of key names used in this plan

- `SYNC_EXPERIMENTS_REQUEST` — request topic, `"ssh_service/request/sync_experiments"`
- `SYNC_EXPERIMENTS_STARTED` — ack topic, `"ssh_service/started/sync_experiments"`
- `SYNC_EXPERIMENTS_SUCCESS` — success topic, `"ssh_service/success/sync_experiments"`
- `SYNC_EXPERIMENTS_ERROR` — error topic, `"ssh_service/error/sync_experiments"`
- `experiments_sync_publisher` — module-level `ExperimentsSyncRequestPublisher` instance in `ssh_controls/consts.py`
- `sync_listener_name` — `"ssh_controls_ui_sync_listener"` — the Dramatiq listener name for the sync dialog's response topics
- `listener_name` — `"ssh_controls_listener"` / `"ssh_controls_ui_listener"` — the *existing* listener names, unchanged
- `SyncDialogModel` / `SyncDialogViewModel` / `SyncDialogView` / `SyncDialogListener` — the four MVVM components in `ssh_controls_ui/sync_dialog/`
- `SyncDialogApp` — `QMainWindow` wrapper in `ssh_controls_ui/menus.py`
- `ShowSyncRemoteExperimentsAction` — Pyface Action in `ssh_controls_ui/menus.py`
- `SERVICE_PLUGINS` — new plugin list in `examples/plugin_consts.py` containing `SSHControlsPlugin`
- `TIMEOUT_MS` — 60000, the pre-prompt wait window in `SyncDialogViewModel`
