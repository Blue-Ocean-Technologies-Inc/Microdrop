import sys
import os
import signal
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import redis

from dramatiq import set_broker
from dramatiq.brokers.redis import RedisBroker

from examples.run_device_viewer_pluggable import main as run_device_viewer_pluggable
from examples.plugin_consts import *


def main(args):
    REDIS_PORT = 50000


    # Create a Redis client instance
    r = redis.StrictRedis(
        port=REDIS_PORT,
    )


    set_broker(RedisBroker(client=r))

    """Run only the backend plugins."""
    plugins = REQUIRED_PLUGINS + BACKEND_PLUGINS
    contexts = BACKEND_CONTEXT + REQUIRED_CONTEXT
    
    run_device_viewer_pluggable(plugins=plugins, contexts=contexts, application=BACKEND_APPLICATION, persist=True)


if __name__ == "__main__":
    main(sys.argv)
