# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import redis
import multiprocessing
import time
from microdrop_utils.broker_server_helpers import redis_server_context

# Redis connection setup
REDIS_HOST = "localhost"
REDIS_PORT = 6379


def redis_client():
    return redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


# Function for Process 1
def process1():
    client = redis_client()
    for i in range(5):
        client.hset("my_dict", f"key1_{i}", f"value1_{i}")
        time.sleep(0.1)  # Simulate processing time


# Function for Process 2
def process2():
    client = redis_client()
    for i in range(5):
        client.hset("my_dict", f"key2_{i}", f"value2_{i}")
        time.sleep(0.1)  # Simulate processing time


# The test function
def test_concurrent_redis_updates():

    # Start the two processes
    p1 = multiprocessing.Process(target=process1)
    p2 = multiprocessing.Process(target=process2)

    p1.start()
    p2.start()

    p1.join()
    p2.join()

    # Verify the final dictionary
    client = redis_client()
    my_dict = client.hgetall("my_dict")

    # Validate expected keys and values
    expected_keys = {f"key1_{i}" for i in range(5)} | {f"key2_{i}" for i in range(5)}
    expected_values = {f"value1_{i}" for i in range(5)} | {f"value2_{i}" for i in range(5)}

    assert set(my_dict.keys()) == expected_keys, "Keys in the Redis dictionary do not match expected keys"
    assert set(my_dict.values()) == expected_values, "Values in the Redis dictionary do not match expected values"
