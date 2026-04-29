"""Tree-level conftest. Calls configure_dramatiq_broker() at module
import time so all actor registrations land on the same broker the
Redis-required tests will use. Non-Redis tests are unaffected (they
mock publish_message and never enqueue to Redis).

Mirrors dropbot_protocol_controls/tests/conftest.py from PPT-4."""

from microdrop_utils.broker_server_helpers import configure_dramatiq_broker

configure_dramatiq_broker()
