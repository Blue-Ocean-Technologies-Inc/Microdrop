"""
Integration test for the SYNC_EXPERIMENTS_REQUEST round-trip through
the ssh_controls service. Requires a running Redis server (see
examples/start_redis_server.py) because SSHService()'s constructor
registers a Dramatiq actor, which needs the broker to be initialized.

Rsync is stubbed; no SSH traffic is generated.
"""
import json
import subprocess
import threading
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

    service = SSHService()

    with patch.object(svc, "Rsync") as MockRsync:
        MockRsync.return_value.sync.side_effect = _fake_rsync_ok
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
    bad = dict(VALID_PAYLOAD)
    del bad["dest"]

    service._on_sync_experiments_request(json.dumps(bad))

    topics = topic_collector.topics
    assert SYNC_EXPERIMENTS_ERROR in topics
    assert SYNC_EXPERIMENTS_STARTED not in topics
    assert SYNC_EXPERIMENTS_SUCCESS not in topics
