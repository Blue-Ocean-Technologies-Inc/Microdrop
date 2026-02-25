import json
import pytest
from pydantic import ValidationError

from electrode_controller.models import ElectrodeChannelsRequest


# --- Happy Path Tests ---

def test_valid_electrode_request():
    """Test that a valid list of integers within bounds passes validation as a set."""
    payload = {"actuated_channels": [0, 2, 5]}
    context = {"max_channels": 10}

    model = ElectrodeChannelsRequest.model_validate(payload, context=context)

    # Note: Asserting against a set, not a list
    assert model.actuated_channels == {0, 2, 5}

def test_empty_list_is_valid():
    """Test that an empty list is technically valid (no bounds violated)."""
    payload = {"actuated_channels": []}
    context = {"max_channels": 10}

    model = ElectrodeChannelsRequest.model_validate(payload, context=context)

    # Note: Asserting against an empty set
    assert model.actuated_channels == set()

def test_duplicate_values_are_deduplicated():
    """Test that providing duplicate values automatically resolves to a unique set."""
    payload = {"actuated_channels": [1, 2, 2, 5, 5]}
    context = {"max_channels": 10}

    model = ElectrodeChannelsRequest.model_validate(payload, context=context)

    assert model.actuated_channels == {1, 2, 5}


# --- Type Validation Tests (StrictInt) ---

def test_rejects_floats():
    """Test that StrictInt rejects floats, even if they equal an integer (e.g., 2.0)."""
    payload = {"actuated_channels": [1, 2.0, 3]}
    context = {"max_channels": 10}

    with pytest.raises(ValidationError) as exc_info:
        ElectrodeChannelsRequest.model_validate(payload, context=context)

    assert "Input should be a valid integer" in str(exc_info.value)

def test_rejects_strings():
    """Test that StrictInt rejects string representations of integers."""
    payload = {"actuated_channels": [1, "2", 3]}
    context = {"max_channels": 10}

    with pytest.raises(ValidationError) as exc_info:
        ElectrodeChannelsRequest.model_validate(payload, context=context)

    assert "Input should be a valid integer" in str(exc_info.value)


# --- Bounds Validation Tests ---

def test_rejects_negative_values():
    """Test that values below 0 trigger a ValueError."""
    payload = {"actuated_channels": [-1, 2, 3]}
    context = {"max_channels": 10}

    with pytest.raises(ValidationError) as exc_info:
        ElectrodeChannelsRequest.model_validate(payload, context=context)

    assert "Values must be >= 0" in str(exc_info.value)

def test_rejects_values_above_max_channels():
    """Test that values exceeding the dynamically injected max_channels trigger a ValueError."""
    payload = {"actuated_channels": [1, 2, 11]}
    context = {"max_channels": 10}

    with pytest.raises(ValidationError) as exc_info:
        ElectrodeChannelsRequest.model_validate(payload, context=context)

    assert "Values must be >= 0 and <= 10" in str(exc_info.value)


# --- Structural Validation Tests ---

def test_missing_key_rejected():
    """Test that failing to provide the 'actuated_channels' key raises an error."""
    payload = {"wrong_key": [1, 2, 3]}
    context = {"max_channels": 10}

    with pytest.raises(ValidationError) as exc_info:
        ElectrodeChannelsRequest.model_validate(payload, context=context)

    assert "Field required" in str(exc_info.value)

def test_non_list_payload_rejected():
    """Test that providing a single integer instead of a list/set fails."""
    payload = {"actuated_channels": 5}
    context = {"max_channels": 10}

    with pytest.raises(ValidationError) as exc_info:
        ElectrodeChannelsRequest.model_validate(payload, context=context)

    # Pydantic may say 'valid list' or 'valid set' depending on the exact parsing phase,
    # so we just look for the base error type
    assert "Input should be a valid" in str(exc_info.value)


# --- Message Creation & JSON Handling Tests ---

def test_json_dump():
    """Test that the model dumps correctly to a JSON string. Even with a set input"""
    data = {"actuated_channels": {1, 2, 5}}

    message = ElectrodeChannelsRequest(actuated_channels=data["actuated_channels"])
    dumped_json = json.loads(message.model_dump_json())

    assert type(dumped_json["actuated_channels"]) == list

    # Sets are unordered, so when Pydantic dumps it back to a JSON list, the order isn't guaranteed.
    # Casting the dumped list to a set ensures the test is robust.
    assert set(dumped_json["actuated_channels"]) == {1, 2, 5}

def test_json_validate():
    """Test that validating from a raw JSON string works properly."""
    data = json.dumps({"actuated_channels": [1, 2, 5]})
    context = {"max_channels": 10}

    model = ElectrodeChannelsRequest.model_validate_json(data, context=context)

    assert model.actuated_channels == {1, 2, 5}

def test_model_instantiation_failure():
    """Test that standard instantiation fails when provided invalid data types or out-of-bounds values."""

    # Test strict int failure
    data = {"actuated_channels": [1, 2, 5, "2"]}
    with pytest.raises(ValidationError) as exc_info:
        ElectrodeChannelsRequest(actuated_channels=data["actuated_channels"])

    assert "Input should be a valid integer" in str(exc_info.value)

    # Test bounds failure during standard instantiation (requires context if checking upper bound)
    # Here we check the lower bound since the upper bound defaults to inf without context
    data = {"actuated_channels": [1, 2, 5, -2]}
    with pytest.raises(ValidationError) as exc_info:
        ElectrodeChannelsRequest(actuated_channels=data["actuated_channels"])

    assert "Bounds validation failed" in str(exc_info.value)