import pytest
from pydantic import ValidationError

from peripheral_controller.datamodels import ZStageConfigData


# --- JSON Parsing Tests ---

def test_valid_json_input():
    """Test that valid JSON with floats parses correctly."""
    # down (10.5) < up (20.1) -> Valid
    json_str = '{"zstage_down_position": 10.5, "zstage_up_position": 20.1}'

    model = ZStageConfigData.model_validate_json(json_str)

    assert model.zstage_down_position == 10.5
    assert model.zstage_up_position == 20.1
    assert isinstance(model.zstage_down_position, float)


def test_valid_json_coercion():
    """
    Test that Pydantic converts strings/ints to floats automatically.
    """
    # Updated values to satisfy up > down rule
    # down="10" -> 10.0, up="50.5" -> 50.5
    json_str = '{"zstage_down_position": "10", "zstage_up_position": "50.5"}'

    model = ZStageConfigData.model_validate_json(json_str)

    assert model.zstage_down_position == 10.0
    assert model.zstage_up_position == 50.5


def test_extra_fields_forbidden():
    """Test that extra fields cause a validation error."""
    json_str = '''
    {
        "zstage_down_position": 10.0, 
        "zstage_up_position": 20.0, 
        "zstage_speed": 5.0
    }
    '''

    with pytest.raises(ValidationError) as excinfo:
        ZStageConfigData.model_validate_json(json_str)

    assert "Extra inputs are not permitted" in str(excinfo.value)


def test_missing_field():
    """Test that missing fields raise a validation error."""
    json_str = '{"zstage_down_position": 10.0}'

    with pytest.raises(ValidationError) as excinfo:
        ZStageConfigData.model_validate_json(json_str)

    assert "Field required" in str(excinfo.value)


def test_invalid_data_type():
    """Test that non-numeric strings raise a validation error."""
    json_str = '{"zstage_down_position": "Not a number", "zstage_up_position": 20.0}'

    with pytest.raises(ValidationError) as excinfo:
        ZStageConfigData.model_validate_json(json_str)

    assert "Input should be a valid number" in str(excinfo.value)


def test_negative_values_forbidden():
    """Test that negative numbers raise a validation error."""

    # Test 0.0 boundary (Valid as long as up > down)
    json_valid = '{"zstage_down_position": 0.0, "zstage_up_position": 0.1}'
    model = ZStageConfigData.model_validate_json(json_valid)
    assert model.zstage_down_position == 0.0

    # Test Negative Value (Should fail)
    json_invalid = '{"zstage_down_position": -0.1, "zstage_up_position": 10.0}'

    with pytest.raises(ValidationError) as excinfo:
        ZStageConfigData.model_validate_json(json_invalid)

    assert "Input should be greater than or equal to 0" in str(excinfo.value)


def test_up_position_must_be_larger():
    """Test the new logic: Up must be strictly larger than Down."""

    # Case 1: Up < Down (Should Fail)
    json_invalid_order = '{"zstage_down_position": 20.0, "zstage_up_position": 10.0}'
    with pytest.raises(ValidationError) as excinfo:
        ZStageConfigData.model_validate_json(json_invalid_order)
    assert "zstage_up_position must be strictly larger than zstage_down_position" in str(excinfo.value)

    # Case 2: Up == Down (Should Fail, assuming strict inequality)
    json_equal = '{"zstage_down_position": 10.0, "zstage_up_position": 10.0}'
    with pytest.raises(ValidationError) as excinfo:
        ZStageConfigData.model_validate_json(json_equal)
    assert "zstage_up_position must be strictly larger than zstage_down_position" in str(excinfo.value)


# --- Python Constructor (Creation) Tests ---

def test_create_via_constructor_valid():
    """Test direct instantiation via Python class constructor."""
    config = ZStageConfigData(zstage_down_position=5.0, zstage_up_position=15.0)
    assert config.zstage_down_position == 5.0
    assert config.zstage_up_position == 15.0


def test_create_via_constructor_extra_forbidden():
    """Test that passing extra arguments to constructor raises ValidationError."""
    with pytest.raises(ValidationError) as excinfo:
        ZStageConfigData(
            zstage_down_position=5.0,
            zstage_up_position=15.0,
            invalid_param=123
        )
    assert "Extra inputs are not permitted" in str(excinfo.value)


def test_create_via_constructor_logic_validation():
    """Test logical constraints (up > down) via constructor."""
    with pytest.raises(ValidationError) as excinfo:
        ZStageConfigData(zstage_down_position=20.0, zstage_up_position=10.0)
    assert "zstage_up_position must be strictly larger than zstage_down_position" in str(excinfo.value)


def test_create_via_constructor_negative_validation():
    """Test negative value constraints via constructor."""
    with pytest.raises(ValidationError) as excinfo:
        ZStageConfigData(zstage_down_position=-5.0, zstage_up_position=10.0)
    assert "Input should be greater than or equal to 0" in str(excinfo.value)


def test_create_dump_validate_cycle():
    """Test the full cycle: Create -> Dump to JSON -> Validate from JSON."""
    # 1. Create the model using Python constructor
    original_model = ZStageConfigData(zstage_down_position=5.5, zstage_up_position=15.5)

    # 2. Dump to JSON string
    json_output = original_model.model_dump_json()

    # 3. Validate (Load back) from that JSON string
    loaded_model = ZStageConfigData.model_validate_json(json_output)

    # 4. Assertions to ensure data integrity
    assert loaded_model.zstage_down_position == original_model.zstage_down_position
    assert loaded_model.zstage_up_position == original_model.zstage_up_position
    # Pydantic models support direct equality checks
    assert loaded_model == original_model