from dropbot.hardware_test import ALL_TESTS
from pyface.tasks.action.api import SMenu, TaskWindowAction
from traits.api import Property, Directory

from microdrop_utils._logger import get_logger

logger = get_logger(__name__)

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from dropbot_controller.consts import RUN_ALL_TESTS, TEST_SHORTS, TEST_VOLTAGE, TEST_CHANNELS, \
    TEST_ON_BOARD_FEEDBACK_CALIBRATION, START_DEVICE_MONITORING

from traits.api import Str, Int, Any

from .consts import PKG

#new
from .self_test_dialogs import SelfTestIntroDialog, ResultsDialog
from PySide6 import QtWidgets
# from dropbot_controller.consts import SELF_TESTS_PROGRESS
import json
from bs4 import BeautifulSoup #html parser
import numpy as np
import os
import base64
import tempfile


class DramatiqMessagePublishAction(TaskWindowAction):
    topic = Str(desc="topic this action connects to")
    message = Any(desc="message to publish")

    def perform(self, event=None):
        publish_message(topic=self.topic, message=self.message)


class RunTests(DramatiqMessagePublishAction):
    num_tests = Int(1, desc="number of tests run")
    message = Property(Directory, observe="object.application.app_data_dir")

    def _get_message(self):
        if self.object.application:
            return self.object.application.app_data_dir
        return None

    def perform(self, event=None):
        logger.info("Requesting running self tests for dropbot")

        super().perform(event)

def dropbot_tools_menu_factory():
    """
    Create a menu for the Manual Controls
    The Sgroup is a list of actions that will be displayed in the menu.
    In this case there is only one action, the help menu.
    It is contributed to the manual controls dock pane using its show help method. Hence it is a DockPaneAction.
    It fetches the specified method from the dock pane essentially.
    """

    # create new groups with all the possible dropbot self-test options as actions
    test_actions = [
        RunTests(name="Test high voltage", topic=TEST_VOLTAGE),
        RunTests(name='On-board feedback calibration', topic=TEST_ON_BOARD_FEEDBACK_CALIBRATION),
        RunTests(name='Detect shorted channels', topic=TEST_SHORTS),
        RunTests(name="Scan test board", topic=TEST_CHANNELS),
    ]

    test_options_menu = SMenu(items=test_actions, id="dropbot_on_board_self_tests", name="On-board self-tests", )

    # create an action to run all the test options at once
    run_all_tests = RunTests(name="Run all on-board self-tests", topic=RUN_ALL_TESTS, num_tests=len(ALL_TESTS))

    '''
    (from hardware_test.py)
    ALL_TESTS = ['system_info', 'test_system_metrics', 'test_i2c', 'test_voltage',
             'test_shorts', 'test_on_board_feedback_calibration',
             'test_channels']
    '''

    # create an action to restart dropbot search
    dropbot_search = DramatiqMessagePublishAction(name="Search for Dropbot Connection", topic=START_DEVICE_MONITORING)

    # return an SMenu object compiling each object made and put into Dropbot menu under Tools menu.
    return SMenu(items=[run_all_tests, test_options_menu, dropbot_search], id="dropbot_tools", name="Dropbot")


def parse_test_voltage_html_report(html_path):
    """
    Parse the test voltage report and return a dictionary of the results.
    """
    with open(html_path, 'r', encoding='utf-8') as file:
        soup = BeautifulSoup(file, 'html.parser')

    # extract JSON results from the <script id="results"> tag
    script_tag = soup.find('script', {'id': 'results'})
    if not script_tag:
        raise ValueError("No <script id='results'> tag found in the HTML report.")
    
    json_data = json.loads(script_tag.string)

    # extract test voltage results for specific parsing
    voltage_results = json_data.get("test_voltage", {})
    table = []
    if 'target_voltage' in voltage_results and 'measured_voltage' in voltage_results:
        target_voltages = voltage_results['target_voltage']['__ndarray__']
        measured_voltages = voltage_results['measured_voltage']

        # create a table-like structure
        table = ['Target Voltage', 'Measured Voltage']
        for t, m in zip(target_voltages, measured_voltages):
            table.append([f'{t:.2f}', f'{m:.2f}'])

   

    # rms error
    rms_error = voltage_results.get('rms_error', None)

    # plot data
    plot_data = { 
        "x": voltage_results.get("target_voltage", {}).get("__ndarray__", []),
        "y": voltage_results.get("measured_voltage", [])
    }

    return {
        "table": table,
        "rms_error": rms_error,
        "plot_data": plot_data
    }
        
def parse_on_board_feedback_calibration_html_report(html_path):
    """
    Parse the on-board feedback calibration report and return a dictionary of the results.
    """
    with open(html_path, 'r', encoding='utf-8') as file:
        soup = BeautifulSoup(file, 'html.parser')

    # extract JSON results from the <script id="results"> tag
    script_tag = soup.find('script', {'id': 'results'})
    if not script_tag:
        raise ValueError("No <script id='results'> tag found in the HTML report.")
    
    json_data = json.loads(script_tag.string)
    results = json_data.get("test_on_board_feedback_calibration", {})
    c_measured = results.get("c_measured", {}).get("__ndarray__", [])

    # Nominal capacitance values (pF)
    nominal_capacitances = [0.0, 10.0, 100.0, 470.0]  # pF, order matches rows
    table = [["Nominal Capacitance (pF)", "Measured Capacitance (mean, pF)"]]
    x = []
    y = []

    if c_measured and len(c_measured) == 4:  # check if we always expect 4 rows
        for idx, row in enumerate(c_measured):
            if row:
                measured_mean_pf = np.mean(row) * 1e12  # F to pF
                table.append([f"{nominal_capacitances[idx]:.1f}", f"{measured_mean_pf:.2f}"])
                x.append(nominal_capacitances[idx])
                y.append(measured_mean_pf)

    plot_data = {
        "x": x,
        "y": y
    }

    return {
        "table": table,
        "plot_data": plot_data
    }

def parse_scan_test_board_html_report(html_path):
    """
    Parse the scan test board report and return a dictionary.
    Extracts:
      - description_text: Any text before the first plot/image
      - images: paths to PNG images found in <img> tags (file or base64)
    """
    with open(html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')

    images = []
    for img in soup.find_all('img'):
        src = img.get('src', '')
        if src.lower().startswith('data:image/png;base64,'):
            # Extract and decode base64 PNG
            b64_data = src.split('base64,')[1]
            img_bytes = base64.b64decode(b64_data)
            # Save to a temp file
            tmp_dir = tempfile.gettempdir()
            tmp_path = os.path.join(tmp_dir, f'scan_test_board_{len(images)}.png')
            with open(tmp_path, 'wb') as out:
                out.write(img_bytes)
            images.append(tmp_path)
        elif '.png' in src.lower():
            # Relative or absolute file path
            if not os.path.isabs(src):
                src = os.path.join(os.path.dirname(html_path), src)
            images.append(src)

    # Extract description text before first image
    description_text = ""
    body = soup.body
    found_img = False
    if body:
        for tag in body.descendants:
            if getattr(tag, 'name', None) == 'img':
                found_img = True
                break
            if getattr(tag, 'name', None) in ('p', 'div', 'span', 'h1', 'h2', 'h3') and tag.string:
                description_text += tag.string.strip() + "\n"
        description_text = description_text.strip()

    return {
        "description_text": description_text,
        "images": images
    }

