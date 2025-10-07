import sys
import os

import redis

from dramatiq import set_broker
from dramatiq.brokers.redis import RedisBroker


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from examples.run_device_viewer_pluggable import main as run_device_viewer_pluggable
from examples.plugin_consts import (REQUIRED_PLUGINS, FRONTEND_PLUGINS,
                                    FRONTEND_CONTEXT, REQUIRED_CONTEXT,
                                    FRONTEND_APPLICATION)


def main():


    REDIS_HOST = "192.168.8.186"
    REDIS_PORT = 50000


    # Create a Redis client instance
    r = redis.StrictRedis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True
    )


    set_broker(RedisBroker(client=r))


    """Run only the frontend plugins."""
    plugins = REQUIRED_PLUGINS + FRONTEND_PLUGINS
    contexts = FRONTEND_CONTEXT + REQUIRED_CONTEXT
    run_device_viewer_pluggable(plugins=plugins, contexts=contexts,
                                application=FRONTEND_APPLICATION, persist=False)


if __name__ == "__main__":
    main()
