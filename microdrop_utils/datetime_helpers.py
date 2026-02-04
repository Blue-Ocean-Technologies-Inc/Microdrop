import json
from typing import Any
import datetime as dt

UTC_TIME_FORMAT = '%Y_%m_%d-%H_%M_%S'

def get_current_utc_datetime():
    return dt.datetime.now(dt.timezone.utc).strftime(UTC_TIME_FORMAT)

def get_elapsed_time_from_utc_datetime(start_time: str, end_time: str):

    # 1. Convert strings back to datetime objects
    t1 = dt.datetime.strptime(start_time, UTC_TIME_FORMAT)
    t2 = dt.datetime.strptime(end_time, UTC_TIME_FORMAT)

    # 2. Calculate the difference (returns a timedelta object)
    duration = t2 - t1

    # 3. Extract components
    hours, remainder = divmod(duration.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    return f"{hours}h {minutes}m {seconds}s"

class TimestampedMessage(str):
    """A string subclass that includes a timestamp attribute."""

    def __new__(cls, content: Any, timestamp: float | None):
        # Convert content to string and create the string instance
        instance = super().__new__(cls, str(content))
        # Store the timestamp as an instance attribute in ISO format
        if timestamp is None:
            timestamp_dt = dt.datetime.min
        else:
            timestamp_dt = dt.datetime.fromtimestamp(timestamp / 1000)

        # Store the timestamp as an instance attribute
        instance._timestamp_dt = timestamp_dt
        instance._timestamp = timestamp_dt.strftime('%Y_%m_%d-%H_%M_%S_%f')
        instance._timestamp_ms = timestamp
        instance._content = content if content not in ["", "None"] else None

        return instance

    def serialize(self) -> str:
        return json.dumps({'message': self, 'timestamp': self._timestamp_ms})

    @staticmethod
    def deserialize(serialized_message: str) -> 'TimestampedMessage':
        data = json.loads(serialized_message)
        return TimestampedMessage(data['message'], data['timestamp'])
  
    @property
    def content(self):
        return self._content

    @property
    def timestamp(self) -> str:
        """Get the timestamp of the message."""
        return self._timestamp

    @property
    def timestamp_dt(self) -> dt.datetime:
        """Get the timestamp of the message as a datetime object."""
        return self._timestamp_dt

    def __repr__(self) -> str:
        return (
            f"TimestampedMessage({super().__repr__()}, "
            f"timestamp={self._timestamp})"
        )
   
    def is_after(self, other: 'TimestampedMessage') -> bool:
        return self._timestamp_dt > other._timestamp_dt
