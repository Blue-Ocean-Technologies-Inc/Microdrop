import numpy as np

from device_viewer.utils.dmf_utils import SvgUtil
from device_viewer.utils.dmf_utils_helpers import SVGProcessor
from pathlib import Path


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

    device = SvgUtil(device_repo / device_120_pin_path)
    check_match(device.connections, device.connections)


# Specify the directory you want to search
directory_path = Path().home() / "Documents" / "Sci-Bots" / "Microdrop" / "Devices"

# Use the .glob() method to find all files matching the pattern
# The pattern '*.svg' means any file ending with .svg
svg_files = list(directory_path.glob('*.svg'))

num_files = len(svg_files)

success_n = 0
# The result is a list of Path objects
for file_path in svg_files:


    device = SvgUtil(filename=file_path)
    if device.neighbours:
        success_n += 1
    else:
        print(file_path)


if success_n == num_files:
    print("*"*10000)
    print("*" * 10000)
    print("All WORK!")
    print("*" * 10000)
    print("*" * 10000)

else:
    print("*"*10000)
    print(f"Only {success_n}/{num_files} worked")
    print("*" * 10000)


# main()


