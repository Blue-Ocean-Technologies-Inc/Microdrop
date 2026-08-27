# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import threading
import concurrent.futures
from dropbot.proxy import SerialProxy

# Create the proxy connection
proxy = SerialProxy()

# Create a lock to ensure thread safety when accessing hardware
lock = threading.Lock()


def access_hardware(thread_id):
    """Function to access hardware based on thread_id."""
    with lock:  # Ensure only one thread accesses proxy at a time
        if thread_id % 2:
            shorts = proxy.detect_shorts(10)
            print(f"Thread {thread_id}: Shorts detected: {shorts}")
        else:
            ram = proxy.ram_free()
            print(f"Thread {thread_id}: RAM free: {ram}")


def main():
    # Use ThreadPoolExecutor for multithreading
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # Submit hardware access tasks to the thread pool
        futures = [executor.submit(access_hardware, i) for i in range(10)]

        # Wait for all futures to complete
        concurrent.futures.wait(futures)


if __name__ == "__main__":
    main()