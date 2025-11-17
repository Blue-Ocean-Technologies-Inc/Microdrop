import time

from dotenv import load_dotenv
import pytest
import os
import shutil
import subprocess
from microdrop_utils.file_sync_helpers import Rsync
from pathlib import Path
import filecmp

# Define test directory names
SOURCE_DIR = Path(__file__).parent / "rsync_test_source"
DEST_DIR = Path(__file__).parent / "rsync_test_dest"

data = SOURCE_DIR / "data"
logs = SOURCE_DIR / "logs"

file1 = data / "file1.txt"
app_logs = logs / "app_logs.txt"
old_file = DEST_DIR / "old_file.txt"

load_dotenv()
SSH_IDENTITY = os.getenv("SSH_PRIVATE_KEY_FILE")
SSH_USERNAME = os.getenv("REMOTE_HOST_USERNAME")
SSH_IP = os.getenv("REMOTE_HOST_IP_ADDRESS")
SSH_PORT = os.getenv("REMOTE_SSH_PORT")


@pytest.fixture(scope="function")
def setup_test_dirs():
    """
    Pytest fixture to create dummy source/dest directories and files
    before a test runs, and clean them up after.
    """
    # --- Setup ---
    try:
        data.mkdir(parents=True, exist_ok=True)
        logs.mkdir(parents=True, exist_ok=True)
        DEST_DIR.mkdir(parents=True, exist_ok=True)

        with open(file1, "w") as f:
            f.write("This is file 1.")

        with open(app_logs, "w") as f:
            f.write("Log data...")

        with open(old_file, "w") as f:
            f.write("This file should be deleted.")

        print(f"Created dummy source directory: {SOURCE_DIR}")
        print(f"Created dummy destination directory: {DEST_DIR}")

        # Yield control back to the test function
        yield SOURCE_DIR, DEST_DIR

    finally:
        # --- Teardown ---
        print("\nCleaning up test directories...")
        try:
            shutil.rmtree(SOURCE_DIR)
            shutil.rmtree(DEST_DIR)
            print("Cleanup complete.")
        except Exception as e:
            print(f"Cleanup failed: {e}")
            print(f"Please manually delete '{SOURCE_DIR}' and '{DEST_DIR}'")


def test_local_sync_delete_exclude(setup_test_dirs):
    """
    Tests a basic local sync with --delete and --exclude options.
    Corresponds to Example 1 from the original file.
    """
    # setup_test_dirs fixture has already run
    source_dir, dest_dir = setup_test_dirs

    rsync = Rsync()

    try:
        result = rsync.sync(
            src=f"{source_dir}{os.sep}",
            dest=str(dest_dir),
            archive=True,
            verbose=True,
            progress=True,
            delete=True,
            exclude=["*logs"]  # Exclude the 'logs' directory
        )

        print("\nSync successful (Example 1).")
        print("STDOUT:")
        print(result.stdout)

        time.sleep(5)

        # --- Verification using Assertions ---
        assert file1.exists()
        assert logs.exists() == True
        assert (DEST_DIR / "logs").exists() == False
        assert old_file.exists() == False
        assert result.returncode == 0


    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        pytest.fail(f"Sync failed unexpectedly: {e}")


def test_remote_sync_syntax_failure(setup_test_dirs):
    """
    Tests that a simulated remote sync fails gracefully when check=False.
    Corresponds to Example 2 from the original file.
    """
    source_dir, _ = setup_test_dirs

    rsync = Rsync()

    result_remote = rsync.sync(
        src=f"{source_dir}{os.sep}",
        dest="user@remote-host:/backup/",
        archive=True,
        verbose=True,
        identity=SSH_IDENTITY,
        ssh_port=2222,
        check=False  # Prevent raising error on (likely) failure
    )

    print("\nRemote command executed (or failed gracefully).")

    # We expect this to fail because the host doesn't exist
    assert "Could not resolve hostname remote-host" in result_remote.stderr
    if result_remote.stderr:
        print("STDERR:")
        print(result_remote.stderr)

def test_remote_sync_success(setup_test_dirs):
    """
    Tests that remote sync works
    """
    source_dir, _ = setup_test_dirs

    rsync = Rsync()

    # send source file to remote
    rsync.sync(
        src=f"{source_dir}",
        dest=f"{SSH_USERNAME}@{SSH_IP}:~",
        archive=True,
        verbose=True,
        identity=SSH_IDENTITY,
        ssh_port=SSH_PORT,
    )

    # get it back
    # send source file to remote
    result_from = source_dir.with_stem("rsync_test_source_from_remote")
    rsync.sync(
        src=f"{SSH_USERNAME}@{SSH_IP}:~/{source_dir.stem}/",
        dest=f"{source_dir.with_stem("rsync_test_source_from_remote")}",
        archive=True,
        verbose=True,
        identity=SSH_IDENTITY,
        ssh_port=SSH_PORT,
    )

    # run a diff between the two directories
    dcmp = filecmp.dircmp(source_dir, result_from)
    assert dcmp.common_dirs == ['data', 'logs']

    common_files = []
    for sd in dcmp.subdirs.values():
        common_files.extend(sd.common_files)

    assert common_files == ['file1.txt', 'app_logs.txt']



