from envisage.api import Plugin
from traits.api import List
import dramatiq
from dramatiq.brokers.rabbitmq import RabbitmqBroker
import threading

from microdrop_utils.dramatiq_pub_sub_helpers import MessageRouterActor
from microdrop_utils._logger import get_logger

logger = get_logger(__name__)

rabbitmq_broker = RabbitmqBroker(url="amqp://guest:guest@localhost/")
dramatiq.set_broker(rabbitmq_broker)

for el in dramatiq.get_broker().middleware:
    if el.__module__ == "dramatiq.middleware.prometheus":
        dramatiq.get_broker().middleware.remove(el)


class ProtocolGridBackendPlugin(Plugin):
    id = 'app.protocol_grid_backend'
    name = 'Protocol Grid Backend Plugin'
    service_offers = List(contributes_to='envisage.service_offers')

    def start(self):
        super().start()
        self.pgc_service = self._create_service()
        logger.info("ProtocolGC Backend Plugin started")
        self.register_subscribers()
        self._start_worker()

    def register_subscribers(self):
        self.message_router = self.application.get_service(MessageRouterActor)
        if self.message_router is not None:
            # Use the message_router_actor instance as needed
            print("MessageRouterActor service accessed successfully.")
            for actor_name, topics_list in self.pgc_service.actor_topics_dict.items():
                for topic in topics_list:
                    # figure out how to set up message router plugin
                    self.message_router.message_router_data.add_subscriber_to_topic(topic, actor_name)
        else:
            print("MessageRouterActor service not found.")
            return

    def _create_service(self, *args, **kwargs):
        from protocol_grid_controller.services.protocol_grid_structure_services import ProtocolGridStructureService
        return ProtocolGridStructureService()

    def _start_worker(self):
        from dramatiq import Worker

        worker = Worker(broker=rabbitmq_broker)
        worker_thread = threading.Thread(target=worker.start)
        worker_thread.daemon = True
        worker_thread.start()