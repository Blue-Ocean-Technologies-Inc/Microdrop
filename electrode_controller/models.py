from pydantic import BaseModel, StrictInt, field_validator
from pydantic_core.core_schema import ValidationInfo
from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher


class ElectrodeChannelsRequest(BaseModel):
    """
    Validates requests to change electrode states.

    Expects a dictionary with a single key 'actuated_channels' containing
    a 1D array (list) of strictly integers. Ensures values fall within a
    valid range [0, max_channels], where max_channels is provided via context.

    Examples:
        >>> data = {"channels": [1, 2, 3]}
        >>> request = ElectrodeChannelsRequest.model_validate(
        ...     data, context={'max_channels': 5}
        ... )
        >>> request.channels
        {1, 2, 3}
    """
    # Using StrictInt ensures it strictly accepts a 1D array of integers
    channels: set[StrictInt]

    @field_validator("channels")
    @classmethod
    def validate_channel_bounds(cls, values: set[int], info: ValidationInfo):
        if info.context and "max_channels" in info.context:
            max_val = info.context["max_channels"]
        else:
            max_val = float('inf')

        # Check minimum boundary (0) and max based on context
        if any(val < 0 or val > max_val for val in values):
            raise ValueError(f"Bounds validation failed: Values must be >= 0 and <= {max_val}.")

        return values

class ElectrodeStateChangePublisher(ValidatedTopicPublisher):
    validator_class = ElectrodeChannelsRequest

    def publish(self, actuated_channels: set[int], *args, **kwargs):
        """
        Construct payload for publisher using the actuated channels set.
        """
        super().publish({"channels": actuated_channels}, *args, **kwargs)


class ElectrodeDisableRequestPublisher(ValidatedTopicPublisher):
    """
    Publisher for electrode disable requests.
    Reuses ElectrodeChannelsRequest since disabled channels are also a set of channel integers.
    """
    validator_class = ElectrodeChannelsRequest

    def publish(self, disabled_channels: set[int], *args, **kwargs):
        """
        Construct payload for publisher using the disabled channels set.
        """
        super().publish({"channels": disabled_channels}, *args, **kwargs)


class DisabledChannelsChangedPublisher(ValidatedTopicPublisher):
    """
    Publisher for notifying that the hardware's disabled channels have changed.
    Sent by the backend when the proxy's disabled_channels_mask changes
    (e.g., after a halted event or actuation discrepancy).
    """
    validator_class = ElectrodeChannelsRequest

    def publish(self, disabled_channels: set[int], *args, **kwargs):
        """
        Construct payload for publisher using the disabled channels set.
        """
        super().publish({"channels": disabled_channels}, *args, **kwargs)
