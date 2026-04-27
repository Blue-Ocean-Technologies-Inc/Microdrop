"""Unit tests for ssh_controls.models — ExperimentsSyncRequest validation."""

import json

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
        parsed = json.loads(captured["message"])
        assert parsed["host"] == VALID_PAYLOAD["host"]
        assert parsed["port"] == VALID_PAYLOAD["port"]
        assert parsed["identity_path"] == VALID_PAYLOAD["identity_path"]

    def test_publish_raises_on_invalid_payload(self):
        publisher = ExperimentsSyncRequestPublisher(topic="ssh_service/request/sync_experiments")
        with pytest.raises(ValidationError):
            publisher.publish(
                host="192.168.1.10",
                port="not-a-number",
                username="u",
                identity_path="/p",
                src="s",
                dest="d",
            )
