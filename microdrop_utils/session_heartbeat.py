# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Session liveness for router listener queues, and the sweep of dead ones.

Every MicroDrop process owns one ``_<uuid>`` listener queue. A clean exit
withdraws its subscriptions and drops the queue; a crash leaves both behind,
and the router keeps filling the orphaned queue forever. Each process
therefore advertises its queue with an expiring heartbeat key, and on
startup sweeps every listener queue that has none.
"""

# Standard library imports.
import os
import socket
import threading
from collections import defaultdict

# Third-party imports.
from dramatiq.common import q_name
from redis.exceptions import RedisError

# Enthought library imports.
from traits.api import HasTraits, Instance, Int, Property, Str

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import LISTENER_QUEUE_PREFIX

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Prefix of the Redis key advertising that a listener queue's owner is alive.
SESSION_HEARTBEAT_KEY_PREFIX = "microdrop:session:"

#: Prefix of dramatiq's per-broker ack sets, under the broker namespace.
DRAMATIQ_ACKS_PREFIX = "__acks__."

#: Suffix of the hash holding a dramatiq queue's message bodies.
DRAMATIQ_MESSAGES_SUFFIX = ".msgs"


class SessionHeartbeat(HasTraits):
    """Keep ``microdrop:session:<listener_queue>`` alive while we run."""

    #: Client the heartbeat key is written through.
    redis_client = Instance("redis.Redis")

    #: The listener queue this process consumes; names the heartbeat key.
    listener_queue = Str()

    #: Seconds the key outlives its last refresh — how long a crashed
    #: session still looks alive to a starting sibling.
    ttl_s = Int(60)

    #: Seconds between refreshes; must stay well under ``ttl_s``.
    refresh_s = Int(15)

    #: The heartbeat key in Redis.
    key = Property(Str, observe="listener_queue")

    #: Set to stop the refresh thread.
    _stop_event = Instance(threading.Event)

    #: Daemon thread refreshing the key every ``refresh_s``.
    _refresh_thread = Instance(threading.Thread)

    def _get_key(self):
        return session_heartbeat_key(self.listener_queue)

    def start(self):
        """Write the key now, then keep refreshing it until ``stop``."""
        self._write_key()

        self._stop_event = threading.Event()
        self._refresh_thread = threading.Thread(
            target=self._refresh_until_stopped,
            name=f"session-heartbeat-{self.listener_queue}",
            daemon=True,
        )
        self._refresh_thread.start()

        logger.debug(f"session heartbeat started: {self.key}")

    def stop(self):
        """Stop refreshing and withdraw the key."""

        if self._refresh_thread is not None:
            self._stop_event.set()
            self._refresh_thread.join(timeout=1)

        try:
            self.redis_client.delete(self.key)
        except RedisError as error:
            logger.warning(f"session heartbeat {self.key} not withdrawn: {error}")

        logger.debug(f"session heartbeat stopped: {self.key}")

    def _write_key(self):
        owner = f"{socket.gethostname()}:{os.getpid()}"
        self.redis_client.set(self.key, owner, ex=self.ttl_s)

    def _refresh_until_stopped(self):
        while not self._stop_event.wait(self.refresh_s):
            try:
                self._write_key()
            except RedisError as error:
                # A missed refresh is survivable while the key's TTL lasts.
                logger.warning(f"session heartbeat {self.key} not refreshed: {error}")


def session_heartbeat_key(listener_queue):
    """Return the Redis key advertising that ``listener_queue`` is alive."""
    return f"{SESSION_HEARTBEAT_KEY_PREFIX}{listener_queue}"


def is_session_alive(redis_client, listener_queue):
    """Return whether ``listener_queue``'s owning process holds a heartbeat."""
    return bool(redis_client.exists(session_heartbeat_key(listener_queue)))


def listener_queue_from_dramatiq_key(key, namespace="dramatiq"):
    """Return the listener queue a dramatiq Redis key belongs to, or ``None``.

    Covers the queue's own keys (``<ns>:<q>``, ``<ns>:<q>.msgs``, and the
    ``.DQ``/``.XQ`` variants of both) and the per-broker ack sets
    (``<ns>:__acks__.<broker id>.<q>``). Keys of shared queues and dramatiq's
    own bookkeeping (``__heartbeats__``, …) give ``None``.
    """

    if isinstance(key, bytes):
        key = key.decode()

    namespace_prefix = f"{namespace}:"

    if not key.startswith(namespace_prefix):
        return None

    name = key.removeprefix(namespace_prefix)

    if name.startswith(DRAMATIQ_ACKS_PREFIX):
        # Broker ids are uuid4 strings, so the first dot ends the id.
        _broker_id, _, name = name.removeprefix(DRAMATIQ_ACKS_PREFIX).partition(".")

    queue = q_name(name.removesuffix(DRAMATIQ_MESSAGES_SUFFIX))

    # Listener queues are "_" + uuid4; double-underscore names are dramatiq's.
    if queue.startswith("__") or not queue.startswith(LISTENER_QUEUE_PREFIX):
        return None

    return queue


def sweep_dead_listener_queues(broker, router_data, own_queue):
    """Purge the listener queues of sessions that died without cleaning up.

    A candidate is any listener queue named in the subscriber map or owning
    dramatiq keys in Redis; it is dead when no heartbeat key exists for it.
    Each dead queue's subscriptions are withdrawn first, so the router stops
    filling it, then its messages, delay/dead-letter queues and every
    broker's ack set for it are deleted.

    Parameters
    ----------
    broker : dramatiq.brokers.redis.RedisBroker
        The broker whose Redis holds the queues.
    router_data : MessageRouterData
        The router's subscriber map.
    own_queue : str
        This process's listener queue; never swept.
    """

    client = broker.client
    namespace = broker.namespace

    # One read of the map. A sibling process writes its heartbeat before
    # any of its pairs reach the map, so every listener queue seen here
    # either has a live heartbeat or belongs to a dead session.
    mapped_queues = {
        queue
        for pairs in router_data.topic_subscriber_map.values()
        for _, queue in pairs
    }

    # "<ns>:_*" also matches "<ns>:__acks__.*"; the helper sorts them out.
    dramatiq_keys_by_queue = defaultdict(list)

    for key in client.scan_iter(match=f"{namespace}:_*"):
        queue = listener_queue_from_dramatiq_key(key, namespace)

        if queue is not None:
            dramatiq_keys_by_queue[queue].append(key)

    candidates = {
        queue
        for queue in mapped_queues | dramatiq_keys_by_queue.keys()
        if queue.startswith(LISTENER_QUEUE_PREFIX)
    }
    candidates.discard(own_queue)

    dead_queues = {queue for queue in candidates if not is_session_alive(client, queue)}

    if not dead_queues:
        logger.debug("no dead listener queues to sweep")

        return

    changed_topics = router_data.prune_dead_listener_queues(dead_queues)

    for queue in sorted(dead_queues):
        broker.flush(queue)

        # flush clears the queue and this broker's ack set for it, but not
        # the ack sets the dead session's own broker left behind.
        leftover_keys = dramatiq_keys_by_queue.get(queue)

        if leftover_keys:
            # DEL, not UNLINK: the Windows pixi env ships Redis 3.0 (no UNLINK).
            client.delete(*leftover_keys)

        logger.debug(f"swept dead listener queue {queue}")

    logger.info(
        f"swept {len(dead_queues)} dead listener queue(s) and pruned "
        f"{len(changed_topics)} topic subscription list(s) left by crashed sessions"
    )
