import sys
from pathlib import Path

# add microdrop module to path to access other submodules in microdrop (e.g. microdrop_utils)
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from examples.run_device_viewer_pluggable import main as run_device_viewer_pluggable
from examples.plugin_consts import REQUIRED_PLUGINS, FRONTEND_PLUGINS, REQUIRED_CONTEXT, FRONTEND_APPLICATION, \
    DROPBOT_FRONTEND_PLUGINS, OPENDROP_FRONTEND_PLUGINS, PORTABLE_DROPBOT_FRONTEND_PLUGINS


def main(args):
    """Run only the frontend plugins."""

    # You can now access the validated device choice here
    print(f"Starting with device: {args.device}")

    plugins = REQUIRED_PLUGINS + FRONTEND_PLUGINS

    if args.device == "dropbot":
        plugins += DROPBOT_FRONTEND_PLUGINS
    elif args.device == "opendrop":
        plugins += OPENDROP_FRONTEND_PLUGINS
    elif args.device == "portable_dropbot":
        plugins += PORTABLE_DROPBOT_FRONTEND_PLUGINS

    run_device_viewer_pluggable(
        plugins=plugins,
        contexts=REQUIRED_CONTEXT,
        application=FRONTEND_APPLICATION,
        persist=False
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the frontend device viewer plugins.")

    parser.add_argument(
        "--device",
        type=str,
        choices=["dropbot", "opendrop", "portable_dropbot"],
        default="dropbot", # Sets a default if the user doesn't provide the flag
        help="Specify the device to use: 'dropbot', 'opendrop', or 'portable_dropbot'"
    )
    main(parser.parse_args())
