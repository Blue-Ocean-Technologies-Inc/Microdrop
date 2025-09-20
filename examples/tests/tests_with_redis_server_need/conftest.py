import pytest
from ..common import redis_client
from microdrop_utils.broker_server_helpers import start_redis_server, stop_redis_server


@pytest.fixture(autouse=True)
def redis_server_context():
    """
    Context manager for apps that make use of dramatiq.
    Ensures proper startup and shutdown routines.
    """

    proc = start_redis_server()
    client = redis_client()
    client.flushall()  # clear all keys in keys databases in Redis

    yield  # This is where the main logic will execute within the context
    client.flushall()
    # Shutdown routine
    stop_redis_server(proc)