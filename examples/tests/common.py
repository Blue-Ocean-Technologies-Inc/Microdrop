# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import os
from dramatiq import Worker
from contextlib import contextmanager

import dropbot as db
import time


@contextmanager
def worker(*args, **kwargs):
    try:
        worker = Worker(*args, **kwargs)
        worker.start()
        yield worker
    finally:
        worker.stop()

@contextmanager
def proxy_context(*args, **kwargs):
    '''
    Context manager wrapper around DropBot proxy.
    '''
    for i in range(2):
        try:
            proxy = db.SerialProxy(*args, **kwargs)
        except ValueError:
            time.sleep(0.5)
            print('Error connecting. Retrying...')
            continue
        try:
            yield proxy
            break
        finally:
            proxy.terminate()
    else:
        raise IOError('Error connecting to DropBot.')



TEST_PATH = os.getenv("TEST_PATH", os.path.dirname(os.path.abspath(__file__)))
TESTING_BOARD_ELECTRODE_CAPACTIANCE_MIN = 7e-12


def redis_client():
    import dramatiq
    return dramatiq.get_broker().client
