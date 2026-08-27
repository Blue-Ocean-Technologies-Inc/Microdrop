# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Unit tests for models/report_contributions.py — flat-mapping contracts
and the validated contribution publishers bound in consts.py."""

import json

import pytest
from pydantic import ValidationError

from pluggable_protocol_tree.models.report_contributions import (
    ProtocolLoggingDataContributionMessage,
    ProtocolLoggingDataContributionPublisher,
    ProtocolLoggingMetadataContributionMessage,
    ProtocolLoggingMetadataContributionPublisher,
)


class TestContributionMessages:

    def test_flat_scalar_mapping_validates(self):
        model = ProtocolLoggingMetadataContributionMessage.model_validate(
            {"Heater Firmware": "v2.1.0", "Target Temperature (C)": 65})
        assert model.root["Heater Firmware"] == "v2.1.0"

    def test_serializes_to_bare_json_object(self):
        """The wire format must be the flat object itself (what the
        listener handlers json.loads into the metadata/data buckets),
        not a wrapper like {"root": {...}}."""
        model = ProtocolLoggingDataContributionMessage.model_validate(
            {"Temperature (C)": 64.5, "step_idx": 3})
        assert json.loads(model.model_dump_json()) == {
            "Temperature (C)": 64.5, "step_idx": 3}

    def test_empty_mapping_rejected(self):
        with pytest.raises(ValidationError):
            ProtocolLoggingMetadataContributionMessage.model_validate({})

    def test_nested_value_rejected(self):
        with pytest.raises(ValidationError):
            ProtocolLoggingDataContributionMessage.model_validate(
                {"readings": [1, 2, 3]})


class TestContributionPublishers:

    def test_publishers_bind_their_validators(self):
        assert (ProtocolLoggingMetadataContributionPublisher.validator_class
                is ProtocolLoggingMetadataContributionMessage)
        assert (ProtocolLoggingDataContributionPublisher.validator_class
                is ProtocolLoggingDataContributionMessage)

    def test_publish_sends_flat_validated_json(self, monkeypatch):
        captured = {}

        def fake_publish_message(message, topic, **kwargs):
            captured["message"] = message
            captured["topic"] = topic

        import microdrop_utils.dramatiq_pub_sub_helpers as pub_sub
        monkeypatch.setattr(pub_sub, "publish_message", fake_publish_message)

        publisher = ProtocolLoggingDataContributionPublisher(
            topic="microdrop/protocol_tree/logging/data")
        publisher.publish({"Temperature (C)": 64.5})

        assert captured["topic"] == "microdrop/protocol_tree/logging/data"
        assert json.loads(captured["message"]) == {"Temperature (C)": 64.5}

    def test_publish_raises_on_invalid_payload(self):
        publisher = ProtocolLoggingMetadataContributionPublisher(
            topic="microdrop/protocol_tree/logging/metadata")
        with pytest.raises(ValidationError):
            publisher.publish({"nested": {"not": "allowed"}})

    def test_consts_singletons_bound_to_their_topics(self):
        from pluggable_protocol_tree.consts import (
            PROTOCOL_LOGGING_DATA_CONTRIBUTION,
            PROTOCOL_LOGGING_METADATA_CONTRIBUTION,
            protocol_logging_data_contribution_publisher,
            protocol_logging_metadata_contribution_publisher,
        )
        assert (protocol_logging_metadata_contribution_publisher.topic
                == PROTOCOL_LOGGING_METADATA_CONTRIBUTION)
        assert (protocol_logging_data_contribution_publisher.topic
                == PROTOCOL_LOGGING_DATA_CONTRIBUTION)
