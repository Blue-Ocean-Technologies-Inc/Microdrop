# This needs to be run as a module: python -m envisage_sample.app

import time
from dramatiq import Worker
from envisage.api import CorePlugin, Application


class ExampleApp(Application):
    def __init__(self, plugins, broker=None):
        super().__init__(plugins=plugins)


def demo():

    from examples.toy_plugins.frontend import UIPlugin, PlotViewPlugin, TableViewPlugin
    from dramatiq import get_broker

    BROKER = get_broker()

    # Note that fully fledged unittests for enthought services is available via
    # https://github.com/enthought/envisage/blob/main/envisage/tests
    # This is just a simple test to show how the services can be used.

    # As well dramatiq has pytests that are comprehensive at https://github.com/Bogdanp/dramatiq/blob/master/tests
    # Again this is just a simple test just for illustration.

###################### Running test on dramatiq actor declaration with the broker ######################################
    # Upon importing the analysis plugin, the dramtic actor should get registerd with the dramatiq broker

    # NOTE: this fails if you import anything that indirectly imports anything containing a dramatic actor. So loggingplugin
    # needs to be imported here as well. This is because the module with loggingplugin also has analysisplugin, so
    # analysis service (which has the dramatic actor) gets imported and thus its actor declared with the broker.

    print("#" * 100)
    print("Testing actor declaration with the broker\n")
    # before...
    assert len(BROKER.get_declared_actors()) == 0
    print(f"Declared actors before: {BROKER.get_declared_actors()}\n")

    # importing plugin with an actor
    from examples.toy_plugins.backend import AnalysisPlugin
    from examples.toy_plugins.backend import LoggingPlugin
    from examples.toy_plugins.backend.toy_service_plugins.analysis.interfaces.i_analysis_service import IAnalysisService

    # after...
    assert len(BROKER.get_declared_actors()) == 1
    print(f"Declared actors after: {BROKER.get_declared_actors()}\n")

######### Running some tests on the application ############################################################################

    # Loading plugins
    plugins = [CorePlugin(), UIPlugin(), PlotViewPlugin(), TableViewPlugin(), AnalysisPlugin(), LoggingPlugin()]
    app = ExampleApp(plugins=plugins)
    app.start()

#########TEST PLUGIN MANAGER AND SERVICE REGISTRY############################################################################

    print("#" * 100)
    print("Testing plugin manager")
    print(app.plugin_manager._plugins)
    # >> [Plugin(id='app.ui.plugin', name='UIPlugin'),
    #  Plugin(id='app.plot.view.plugin', name='Plot View Plugin'),
    #  Plugin(id='app.table.view.plugin', name='Table View Plugin'),
    #  Plugin(id='app.analysis.plugin', name='Analysis Plugin'),
    #  Plugin(id='app.logging.plugin', name='Logging Plugin')]
    print("#" * 100)
    print("Testing service registry")
    print(app.service_registry._services)
    # >> {1: ('envisage_sample.Interfaces.IAnalysisService',
    #   <envisage_sample.services.AnalysisService at 0x1f2379f2980>,
    #   {'type': 'regular'}),
    #  2: ('envisage_sample.Interfaces.IAnalysisService',
    #   <envisage_sample.services.DramatiqAnalysisService at 0x1f235c71260>,
    #   {'type': 'dramatiq', 'id': 'dramatiq_analysis_service'}),
    #  3: ('envisage_sample.Interfaces.ILoggingService',
    #   <bound method LoggingPlugin._create_service of Plugin(id='app.logging.plugin', name='Logging Plugin')>,
    #   {})}
    print("#" * 100)
#########################################################################################################################

    # We notice the following. With the regular analysis service, we have the AnalysisService type service. Its id
    # was not declared as a property at the plugin level. So it does not get published to the yellow pages. But is
    # still available for use.
    # The DramatiqAnalysisService has an id property declared at the plugin level. So it is
    # published to the yellow pages.
    # This is a good way to control what services are available to the frontend for
    # querying.
    # Also notice that the payload_model is not avaialble for either, it was not declared in the property dict.

################TEST SERVICES################################################################################################

    # Another interesting thing about payload model. It gets overrided at the plugin level even if set at the service
    # class level. Eg below

    regular_task = app.get_service(IAnalysisService, query="type=='regular'")
    dramatiq_task = app.get_service(IAnalysisService, query="type=='dramatiq'")
    print("Testing properties access on services")
    print("#" * 100)
    print(f"Regular task payload overriden to be empty at plugin level: {regular_task.payload_model}")
    # >> ''
    print("#" * 100)
    print(f"Dramatic task Payload, not overriden at plugin level: {dramatiq_task.payload_model}")
    # >> '{"args_to_sum": []}'
    print("#" * 100)

#########################################################################################################################

    # Accessing the views contributed by plugins
    ui_plugin = app.get_plugin('app.ui.plugin')
    print("Available views:", ui_plugin.views)
    print("#" * 100)

#########################################################################################################################

    # The blocking nature of each service can be tested
    # But first test normal calls
    # Setting up the payload and some settings
    payload = {"args_to_sum": [1, 2, 3], "sleep_time": 0.1, "reply": 1}
    N_tasks = 3

#########################################################################################################################

    print("Testing regular task")
    result = regular_task.process_task(payload)
    # Received task: {"args_to_sum": [1, 2, 3]}, processing in backend...
    # Analysis result: 6
    print(result == 6)
    # >> True
    print("#" * 100)

##########################################################################################################################

    print("Testing dramatiq task regular call")
    # Dramatiq is a bit different. It can be non-blocking. So we need to wait for the result to come back on diff thread
    # and ensure the workers are running if the .send is invoked. Else same result as before
    result = dramatiq_task.process_task(payload)
    print(result == 6)
    # >> True
    print("#" * 100)

#########################################################################################################################

    print("Testing dramatiq task send call")

    # clear results
    with open("results.txt", "w") as f:
        f.write("")

#########################################################################################################################

    # class Worker:
    """Workers consume messages off of all declared queues and
    distribute those messages to individual worker threads for
    processing.  Workers don't block the current thread so it's
    up to the caller to keep it alive.

    Don't run more than one Worker per process.

    Parameters:
      broker(Broker)
      queues(Set[str]): An optional subset of queues to listen on.  By
        default, if this is not provided, the worker will listen on
        all declared queues.
      worker_timeout(int): The number of milliseconds workers should
        wake up after if the queue is idle.
      worker_threads(int): The number of worker threads to spawn.
    """

#########################################################################################################################

    # start workers
    worker = Worker(broker=BROKER, queues=None, worker_timeout=1000, worker_threads=N_tasks)

    worker.start()
    # spawns 5 threads (3 for the tasks and 2 for managing the tasks)

    # make task blocking and send multiple tasks with no reply here. The results will be written to a file by actor.
    payload["sleep_time"] = 2
    payload["reply"] = 0

    for i in range(N_tasks):
        dramatiq_task.process_task.send(payload)

    print("#" * 100)

    # The result will be printed on the dramatiq worker process
    # You can boot up one by running the following command in a new terminal
    # dramatiq envisage_sample.services
    # Payload model should also have the response queue routing key in the future for a full implementation to
    # get back results

#########################################################################################################################

    time.sleep(1 + (payload["sleep_time"] * N_tasks))
    with open("results.txt") as f:
        results = f.readlines()
        print(results)
        for el in results:
            assert el == "Analysis result: 6\n"
        assert len(results) == N_tasks

    print("All tests passed")

    app.stop()
    worker.stop()


if __name__ == '__main__':
    # insert source and content root to pythonpath
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from dramatiq import get_broker

    from microdrop_utils.broker_server_helpers import start_redis_server, stop_redis_server
    BROKER = get_broker()

    try:
        # start broker server
        start_redis_server()
        demo()
    finally:
        # stop broker server
        stop_redis_server()


