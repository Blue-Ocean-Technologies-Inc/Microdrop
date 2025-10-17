import numpy as np

from device_viewer.utils.dmf_utils import SvgUtil
from device_viewer.utils.dmf_utils_helpers import SVGProcessor

if __name__ == '__main__':

    try:
        from importlib.resources import as_file, files
    except ImportError:
        from importlib_resources import as_file, files

    device_repo = files('device_viewer.resources.devices')

    device_120_pin_path = device_repo / "120_pin_array.svg"
    device_90_pin_path = device_repo / "90_pin_array.svg"

    # @timeit_benchmark(number=1, repeat=1)
    def main():

        def check_match(item1, item2):

            if item1 == item2:

                print("*" * 1000)
                print("GETTING SAME RESULTS")
                print("*" * 1000)

        device = SvgUtil(device_repo / device_90_pin_path)
        check_match(device.connections, device.connections)

    main()