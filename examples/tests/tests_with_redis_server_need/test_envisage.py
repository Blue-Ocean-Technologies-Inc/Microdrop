# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import dramatiq
import pytest

from ..common import worker


@pytest.fixture
def results_file():
    from pathlib import Path
    from examples.tests.common import TEST_PATH
    test_results = Path(TEST_PATH) / "results.txt"
    with open(test_results, "w") as f:
        f.write("")

    return test_results


@pytest.fixture
def setup_app():
    from examples.toy_plugins.frontend import UIPlugin, PlotViewPlugin, TableViewPlugin
    from examples.toy_plugins.backend import LoggingPlugin, AnalysisPlugin
    from envisage.api import CorePlugin, Application

    class ExampleApp(Application):
        def __init__(self, plugins, broker=None):
            super().__init__(plugins=plugins)

    # Assuming `MyApp` and related plugins are defined elsewhere
    plugins = [CorePlugin(), UIPlugin(), PlotViewPlugin(), TableViewPlugin(), AnalysisPlugin(), LoggingPlugin()]
    app = ExampleApp(plugins=plugins)
    app.start()
    return app


def test_analysis_plugin_import():
    print("#" * 100)
    print("Testing actor declaration with the broker\n")

    broker = dramatiq.get_broker()

    # before...
    assert (len(broker.get_declared_actors()) == 0) # its either empty or the message router actor is in there.
    print(f"Declared actors before: {broker.get_declared_actors()}\n")

    # importing plugin with an actor
    from examples.toy_plugins.backend import AnalysisPlugin

    # after...
    assert (len(broker.get_declared_actors()) == 1)
    print(f"Declared actors after: {broker.get_declared_actors()}\n")


def test_plugin_manager(setup_app):
    app = setup_app
    print("Testing plugin manager")
    assert len(app.plugin_manager._plugins) == 6


def test_service_registry(setup_app):
    app = setup_app
    print("Testing service registry")
    assert len(app.service_registry._services) == 3


def test_service_properties_access_regular(setup_app):

    from examples.toy_plugins.backend.toy_service_plugins.analysis.interfaces.i_analysis_service import IAnalysisService

    app = setup_app
    regular_task = app.get_service(IAnalysisService, query="type=='regular'")
    print("Testing properties access on regular service")
    assert len(regular_task.payload_model) == 0


def test_service_properties_access_dramatiq(setup_app):

    from examples.toy_plugins.backend.toy_service_plugins.analysis.interfaces.i_analysis_service import IAnalysisService

    app = setup_app
    dramatiq_task = app.get_service(IAnalysisService, query="type=='dramatiq'")
    print("Testing properties access on dramatiq service")
    assert len(dramatiq_task.payload_model) != 0


def test_view_access(setup_app):
    app = setup_app
    ui_plugin = app.get_plugin('app.ui.plugin')
    print("Available views:", ui_plugin.views)
    assert len(ui_plugin.views) > 0


def test_regular_task_processing(setup_app):

    from examples.toy_plugins.backend.toy_service_plugins.analysis.interfaces.i_analysis_service import IAnalysisService

    app = setup_app
    regular_task = app.get_service(IAnalysisService, query="type=='regular'")

    payload = {"args_to_sum": [1, 2, 3], "sleep_time": 2}

    print("Testing regular task")
    result = regular_task.process_task(payload)
    assert result == 6


@pytest.fixture
def dramatiq_task_setup(setup_app):

    from examples.toy_plugins.backend.toy_service_plugins.analysis.interfaces.i_analysis_service import IAnalysisService

    app = setup_app
    dramatiq_task = app.get_service(IAnalysisService, query="type=='dramatiq'")
    return dramatiq_task


def test_dramatiq_task_processing_regular_call(dramatiq_task_setup):
    dramatiq_task = dramatiq_task_setup

    payload = {"args_to_sum": [1, 2, 3], "sleep_time": 2}

    print("Testing dramatiq task regular call")
    result = dramatiq_task.process_task(payload)
    assert result == 6


def test_dramatiq_task_send_call(dramatiq_task_setup, results_file):
    from time import sleep

    payload = {"args_to_sum": [1, 2, 3], "sleep_time": 0.1, "reply": 0, "results_file": str(results_file)}
    N_tasks = 5

    # send the tasks in
    for i in range(N_tasks):
        assert dramatiq_task_setup.process_task.send(payload)

    broker = dramatiq.get_broker()
    with worker(broker, worker_timeout=1000) as current_worker:
        broker.join("default")
        current_worker.join()

    # The result will be printed on the dramatiq worker process

    # wait for the job to finish
    sleep(2 + (payload["sleep_time"] * (N_tasks+1)))

    # check the results
    with open(results_file) as f:
        results = f.readlines()
        print(results)
        for el in results:
            assert el == "Analysis result: 6\n"
        assert len(results) == N_tasks