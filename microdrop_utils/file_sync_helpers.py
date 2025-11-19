import subprocess
import os
import platform
from typing import List, Optional, Union
from pathlib import Path


class _RsyncWin:
    """
    A Python wrapper for the rsync-win.exe command-line tool.

    This class builds and executes rsync-win commands using the subprocess
    module, translating Python arguments into command-line flags.

    Attributes:
        executable_path (str): The path to the rsync-win.exe executable.
                               Defaults to 'rsync-win.exe', assuming it's
                               in the system's PATH.
    """

    def __init__(self, executable_path: str = "rsync-win.exe"):
        """
        Initializes the RsyncWin wrapper.

        Args:
            executable_path (str): The path to rsync-win.exe. If the
                                   executable is in your system's PATH,
                                   'rsync-win.exe' is sufficient.
                                   Otherwise, provide the full path,
                                   e.g., r"C:\path\to\rsync-win.exe".
        """
        self.executable_path = executable_path

    def sync(
            self,
            src: str,
            dest: str,
            identity: Optional[str] = None,
            verbose: bool = False,
            quiet: bool = False,
            checksum: bool = False,
            archive: bool = False,
            recursive: bool = False,
            delete: bool = False,
            exclude: Optional[List[str]] = None,
            partial: bool = False,
            progress: bool = False,
            bwlimit: Optional[Union[int, str]] = None,
            ipv4: bool = False,
            ipv6: bool = False,
            ssh_port: Optional[int] = None,
            capture_output: bool = True,
            check: bool = True
    ) -> subprocess.CompletedProcess:
        """
        Executes the rsync-win command with the specified options.

        Args:
            src (str): The source path (e.g., 'C:/data/').
            dest (str): The destination path (e.g., 'user@host:/remote/data/').
            identity (Optional[str]): Path to the SSH identity file.
            verbose (bool): Increase verbosity.
            quiet (bool): Suppress non-error messages.
            checksum (bool): Skip based on checksum, not mod-time & size.
            archive (bool): Archive mode; equals -rltpgoD (no -H,-A,-X).
            recursive (bool): Recurse into directories.
            delete (bool): Delete extraneous files from dest dirs.
            exclude (Optional[List[str]]): A list of patterns to exclude.
            partial (bool): Keep partially transferred files.
            progress (bool): Show progress during transfer.
            bwlimit (Optional[Union[int, str]]): Limit I/O bandwidth; KBytes per sec.
            ipv4 (bool): Prefer IPv4.
            ipv6 (bool): Prefer IPv6.
            ssh_port (Optional[int]): Specify the SSH port.
            capture_output (bool): If True (default), capture stdout and stderr.
                                   If False, output streams to the parent process
                                   (useful for seeing live --progress).
            check (bool): If True (default), raise CalledProcessError on non-zero exit.

        Returns:
            subprocess.CompletedProcess: The result of the command execution.

        Raises:
            FileNotFoundError: If 'rsync-win.exe' (or the specified path) is not found.
            subprocess.CalledProcessError: If rsync-win returns a non-zero exit code
                                           and 'check' is True.
        """
        # Start building the command list
        cmd = [self.executable_path]

        # --- Boolean Flags ---
        # These are added if they are True
        if verbose:
            cmd.append("--verbose")
        if quiet:
            cmd.append("--quiet")
        if checksum:
            cmd.append("--checksum")
        if archive:
            cmd.append("--archive")
        if recursive:
            cmd.append("--recursive")
        if delete:
            cmd.append("--delete")
        if partial:
            cmd.append("--partial")
        if progress:
            cmd.append("--progress")
        if ipv4:
            cmd.append("--ipv4")
        if ipv6:
            cmd.append("--ipv6")

        # --- Options with Values ---
        # These add their flag and the corresponding value
        if bwlimit:
            cmd.append(f"--bwlimit={bwlimit}")

        if identity:
            cmd.extend(["--identity", identity])

        if ssh_port:
            cmd.extend([f"--ssh-port={ssh_port}"])

        # --- List-based Option ---
        # This can be specified multiple times
        if exclude:
            for item in exclude:
                cmd.append(f"--exclude={item}")

        # --- Required Arguments ---
        cmd.extend(["--src", src])
        cmd.extend(["--dest", dest])

        print(f"Executing command: {' '.join(cmd)}")

        try:
            # Execute the command
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                check=check,
                encoding='utf-8'
            )
            return result
        except FileNotFoundError:
            print(f"Error: Executable not found at '{self.executable_path}'")
            print("Please ensure 'rsync-win.exe' is in your system's PATH")
            print("or provide the full path during RsyncWin initialization.")
            raise  # Re-raise the exception
        except subprocess.CalledProcessError as e:
            print(f"Rsync command failed with exit code {e.returncode}")
            if capture_output:
                # If we captured output, print it on error
                print("\nSTDOUT:")
                print(e.stdout)
                print("\nSTDERR:")
                print(e.stderr)
            if check:
                raise  # Re-raise if 'check' was True
            return e  # Otherwise, return the error object


class _RsyncPosix:
    """
    A Python wrapper for the standard POSIX rsync command (Linux, macOS).

    This class builds and executes rsync commands using the subprocess
    module, translating the shared arguments into standard rsync flags.
    """

    def __init__(self, executable_path: str = "rsync"):
        """
        Initializes the RsyncPosix wrapper.

        Args:
            executable_path (str): The path to the rsync executable.
                                   Defaults to 'rsync', assuming it's
                                   in the system's PATH.
        """
        self.executable_path = executable_path

    def sync(
            self,
            src: str,
            dest: str,
            identity: Optional[str] = None,
            verbose: bool = False,
            quiet: bool = False,
            checksum: bool = False,
            archive: bool = False,
            recursive: bool = False,
            delete: bool = False,
            exclude: Optional[List[str]] = None,
            partial: bool = False,
            progress: bool = False,
            bwlimit: Optional[Union[int, str]] = None,
            ipv4: bool = False,
            ipv6: bool = False,
            ssh_port: Optional[int] = None,
            capture_output: bool = True,
            check: bool = True
    ) -> subprocess.CompletedProcess:
        """
        Executes the standard rsync command with the specified options.

        Args:
            src (str): The source path (e.g., '/data/').
            dest (str): The destination path (e.g., 'user@host:/remote/data/').
            identity (Optional[str]): Path to the SSH identity file.
            verbose (bool): Increase verbosity.
            quiet (bool): Suppress non-error messages.
            checksum (bool): Skip based on checksum, not mod-time & size.
            archive (bool): Archive mode; equals -rltpgoD (no -H,-A,-X).
            recursive (bool): Recurse into directories.
            delete (bool): Delete extraneous files from dest dirs.
            exclude (Optional[List[str]]): A list of patterns to exclude.
            partial (bool): Keep partially transferred files.
            progress (bool): Show progress during transfer.
            bwlimit (Optional[Union[int, str]]): Limit I/O bandwidth; KBytes per sec.
            ipv4 (bool): Prefer IPv4.
            ipv6 (bool): Prefer IPv6.
            ssh_port (Optional[int]): Specify the SSH port.
            capture_output (bool): If True (default), capture stdout and stderr.
            check (bool): If True (default), raise CalledProcessError on non-zero exit.

        Returns:
            subprocess.CompletedProcess: The result of the command execution.

        Raises:
            FileNotFoundError: If 'rsync' (or the specified path) is not found.
            subprocess.CalledProcessError: If rsync returns a non-zero exit code
                                           and 'check' is True.
        """
        # Start building the command list
        cmd = [self.executable_path]

        # --- Boolean Flags ---
        if verbose:
            cmd.append("--verbose")
        if quiet:
            cmd.append("--quiet")
        if checksum:
            cmd.append("--checksum")
        if archive:
            cmd.append("--archive")
        if recursive:
            cmd.append("--recursive")
        if delete:
            cmd.append("--delete")
        if partial:
            cmd.append("--partial")
        if progress:
            cmd.append("--progress")
        if ipv4:
            cmd.append("-4")  # Standard rsync flag
        if ipv6:
            cmd.append("-6")  # Standard rsync flag

        if bwlimit:
            cmd.append(f"--bwlimit={bwlimit}")

        if exclude:
            for item in exclude:
                cmd.append(f"--exclude={item}")

        # --- SSH Options (Remote Shell) ---
        # Build the '-e' argument string if ssh_port or identity is provided
        e_str_parts = ["ssh"]
        if ssh_port:
            e_str_parts.extend(["-p", str(ssh_port)])
        if identity:
            e_str_parts.extend(["-i", identity])

        if len(e_str_parts) > 1:
            cmd.extend(["-e", " ".join(e_str_parts)])

        # --- Required Arguments ---
        # Standard rsync takes src and dest as final arguments
        cmd.append(src)
        cmd.append(dest)

        print(f"Executing command: {' '.join(cmd)}")

        try:
            # Execute the command
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                check=check,
                encoding='utf-8'
            )
            return result
        except FileNotFoundError:
            print(f"Error: Executable not found at '{self.executable_path}'")
            print("Please ensure 'rsync' is in your system's PATH.")
            raise  # Re-raise the exception
        except subprocess.CalledProcessError as e:
            print(f"Rsync command failed with exit code {e.returncode}")
            if capture_output:
                # If we captured output, print it on error
                print("\nSTDOUT:")
                print(e.stdout)
                print("\nSTDERR:")
                print(e.stderr)
            if check:
                raise  # Re-raise if 'check' was True
            return e  # Otherwise, return the error object


class Rsync:
    """
    A cross-platform Rsync wrapper.

    This class detects the operating system and uses the appropriate
    backend:
    - Windows: _RsyncWin (for rsync-win.exe)
    - Linux/macOS: _RsyncPosix (for standard rsync)

    The 'sync' method signature is compatible with both, allowing for
    platform-agnostic rsync calls.
    """

    def __init__(
            self,
            windows_executable_path: str = None,
            posix_executable_path: str = None
    ):
        """
        Initializes the correct rsync wrapper based on the OS.

        Args:
            windows_executable_path (str): Path to rsync-win.exe (used on Windows).
            posix_executable_path (str): Path to rsync (used on Linux/macOS).
        """
        self.os_type = platform.system()
        if self.os_type == "Windows":
            if windows_executable_path is None:
                windows_executable_path = Path(__file__).parent / "rsync-win" / "rsync-win.exe"
            self._wrapper = _RsyncWin(executable_path=str(windows_executable_path))
            print("Running on Windows, using rsync-win.exe wrapper.")
        else:
            # Assume Linux, macOS, or other POSIX-like systems
            if posix_executable_path is None:
                posix_executable_path = "rsync"
            self._wrapper = _RsyncPosix(executable_path=posix_executable_path)
            print(f"Running on {self.os_type}, using standard rsync wrapper.")

    def sync(
            self,
            src: str,
            dest: str,
            identity: Optional[str] = None,
            verbose: bool = False,
            quiet: bool = False,
            checksum: bool = False,
            archive: bool = False,
            recursive: bool = False,
            delete: bool = False,
            exclude: Optional[List[str]] = None,
            partial: bool = False,
            progress: bool = False,
            bwlimit: Optional[Union[int, str]] = None,
            ipv4: bool = False,
            ipv6: bool = False,
            ssh_port: Optional[int] = None,
            capture_output: bool = True,
            check: bool = True
    ) -> subprocess.CompletedProcess:
        """
        Executes the rsync command with the specified options using
        the OS-appropriate backend.

        Args:
            src (str): The source path (e.g., 'C:/data/').
            dest (str): The destination path (e.g., 'user@host:/remote/data/').
            identity (Optional[str]): Path to the SSH identity file.
            verbose (bool): Increase verbosity.
            quiet (bool): Suppress non-error messages.
            checksum (bool): Skip based on checksum, not mod-time & size.
            archive (bool): Archive mode; equals -rltpgoD (no -H,-A,-X).
            recursive (bool): Recurse into directories.
            delete (bool): Delete extraneous files from dest dirs.
            exclude (Optional[List[str]]): A list of patterns to exclude.
            partial (bool): Keep partially transferred files.
            progress (bool): Show progress during transfer.
            bwlimit (Optional[Union[int, str]]): Limit I/O bandwidth; KBytes per sec.
            ipv4 (bool): Prefer IPv4.
            ipv6 (bool): Prefer IPv6.
            ssh_port (Optional[int]): Specify the SSH port.
            capture_output (bool): If True (default), capture stdout and stderr.
                                   If False, output streams to the parent process
                                   (useful for seeing live --progress).
            check (bool): If True (default), raise CalledProcessError on non-zero exit.

        Returns:
            subprocess.CompletedProcess: The result of the command execution.

        Raises:
            FileNotFoundError: If the rsync executable is not found.
            subprocess.CalledProcessError: If rsync returns a non-zero exit code
                                           and 'check' is True.
        """
        # Just delegate the call to the chosen wrapper
        return self._wrapper.sync(
            src=src,
            dest=dest,
            identity=identity,
            verbose=verbose,
            quiet=quiet,
            checksum=checksum,
            archive=archive,
            recursive=recursive,
            delete=delete,
            exclude=exclude,
            partial=partial,
            progress=progress,
            bwlimit=bwlimit,
            ipv4=ipv4,
            ipv6=ipv6,
            ssh_port=ssh_port,
            capture_output=capture_output,
            check=check
        )


# --- Example Usage ---
# This block will only run when the script is executed directly
if __name__ == "__main__":

    # 2. Create dummy directories for a safe local test
    SOURCE_DIR = "rsync_test_source"
    DEST_DIR = "rsync_test_dest"

    try:
        os.makedirs(os.path.join(SOURCE_DIR, "logs"), exist_ok=True)
        os.makedirs(os.path.join(SOURCE_DIR, "data"), exist_ok=True)
        os.makedirs(DEST_DIR, exist_ok=True)

        with open(os.path.join(SOURCE_DIR, "data", "file1.txt"), "w") as f:
            f.write("This is file 1.")
        with open(os.path.join(SOURCE_DIR, "logs", "app.log"), "w") as f:
            f.write("Log data...")
        with open(os.path.join(DEST_DIR, "old_file.txt"), "w") as f:
            f.write("This file should be deleted.")

        print(f"Created dummy source directory: {SOURCE_DIR}")
        print(f"Created dummy destination directory: {DEST_DIR}")

        # --- Wrapper Initialization ---
        # Use the new cross-platform Rsync class
        rsync = Rsync()

        # --- Example 1: Local sync, archive, delete, exclude ---
        print("\n--- Example 1: Basic Local Sync (with delete and exclude) ---")
        try:
            result = rsync.sync(
                src=SOURCE_DIR,
                dest=DEST_DIR,
                archive=True,  # Common option: recursive, preserves perms, etc.
                verbose=True,
                progress=True,
                delete=True,  # Delete 'old_file.txt' from dest
                exclude=["logs/"]  # Exclude the 'logs' directory
            )

            print("\nSync successful (Example 1).")
            print("STDOUT:")
            print(result.stdout)

            # Verify
            print("\nVerifying destination (Example 1):")
            print(f"Contents of {DEST_DIR}: {os.listdir(DEST_DIR)}")
            print(f"data/file1.txt exists: {os.path.exists(os.path.join(DEST_DIR, 'data', 'file1.txt'))}")
            print(f"logs/ exists (should be False): {os.path.exists(os.path.join(DEST_DIR, 'logs'))}")
            print(f"old_file.txt exists (should be False): {os.path.exists(os.path.join(DEST_DIR, 'old_file.txt'))}")

        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"\nSync failed (Example 1): {e}")

        # --- Example 2: Simulating a remote sync (syntax check) ---
        print("\n--- Example 2: Remote Sync (Syntax) ---")
        # This will likely fail if you don't have SSH set up,
        # so we use 'check=False' to prevent it from crashing the script.
        result_remote = rsync.sync(
            src=SOURCE_DIR,
            dest="user@remote-host:/backup/",
            archive=True,
            verbose=True,
            identity="C:/.ssh/id_rsa_custom",
            ssh_port=2222,
            check=False  # Prevent raising error on (likely) failure
        )

        print("\nRemote command executed (or failed gracefully).")
        if result_remote.returncode != 0:
            print(f"Command failed as expected. Exit code: {result_remote.returncode}")
            if result_remote.stderr:
                print("STDERR:")
                print(result_remote.stderr)
        else:
            print("Remote sync command successful (unlikely in test).")
            print("STDOUT:")
            print(result_remote.stdout)

    finally:
        # --- Clean up dummy directories ---
        print("\nCleaning up test directories...")
        # This is a simple cleanup. For a robust script, use shutil.rmtree
        try:
            import shutil

            if os.path.exists(SOURCE_DIR):
                shutil.rmtree(SOURCE_DIR)
            if os.path.exists(DEST_DIR):
                shutil.rmtree(DEST_DIR)
            print("Cleanup complete.")
        except OSError as e:
            print(f"Cleanup failed: {e}")
            print(f"Please manually delete '{SOURCE_DIR}' and '{DEST_DIR}'")