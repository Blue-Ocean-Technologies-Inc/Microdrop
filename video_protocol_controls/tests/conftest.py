"""Tree-level conftest. Pre-wires the dramatiq broker so the actors and
Redis-dependent tests added in Tasks 3-9 land on the same broker
configuration. Currently a no-op for the existing plugin-shell tests
(no actors registered yet); kept up-front to mirror PPT-4's conftest
and avoid a later cross-cutting test-infra change."""

from microdrop_utils.broker_server_helpers import configure_dramatiq_broker

configure_dramatiq_broker()
