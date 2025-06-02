from datetime import datetime
import json
from typing import Any


class TimestampedMessage(str):
    """A string subclass that includes a timestamp attribute."""

    def __new__(cls, content: Any, timestamp: float | None):
        # Convert content to string and create the string instance
        instance = super().__new__(cls, str(content))
        # Store the timestamp as an instance attribute in ISO format
        if timestamp is None:
            timestamp_iso = "Timestamp not available"
            timestamp_dt = datetime.min
        else:
            timestamp_dt = datetime.fromtimestamp(timestamp / 1000)
            timestamp_iso = timestamp_dt.isoformat()

        # Store the timestamp as an instance attribute
        instance._timestamp_dt = timestamp_dt
        instance._timestamp = timestamp_iso
        instance._timestamp_ms = timestamp
        return instance
   
    def serialize(self) -> str:
        return json.dumps({'message': self, 'timestamp': self._timestamp_ms})
  
    @staticmethod
    def deserialize(serialized_message: str) -> 'TimestampedMessage':
        data = json.loads(serialized_message)
        return TimestampedMessage(data['message'], data['timestamp'])

    @property
    def timestamp(self) -> str:
        """Get the timestamp of the message."""
        return self._timestamp

    @property
    def timestamp_dt(self) -> datetime:
        """Get the timestamp of the message as a datetime object."""
        return self._timestamp_dt

    def __repr__(self) -> str:
        return (
            f"TimestampedMessage({super().__repr__()}, "
            f"timestamp={self._timestamp})"
        )
   
    def is_after(self, other: 'TimestampedMessage') -> bool:
        return self._timestamp_dt > other._timestamp_dt