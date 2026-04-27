import json
import re
import socket
import subprocess
import warnings

import dramatiq
from paramiko import AuthenticationException
from pydantic import ValidationError
from traits.api import HasTraits, provides, Instance

from logger.logger_service import get_logger
from microdrop_utils import paramiko_helpers
from microdrop_utils.dramatiq_controller_base import (
    IDramatiqControllerBase,
    basic_listener_actor_routine,
    generate_class_method_dramatiq_listener_actor
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.file_sync_helpers import Rsync


from .consts import listener_name, SYNC_EXCEPTIONS_TO_PASS, SSH_KEYGEN_SUCCESS, \
    SSH_KEYGEN_WARNING, SSH_KEYGEN_ERROR, SSH_KEY_UPLOAD_ERROR, SSH_KEY_UPLOAD_SUCCESS, \
    SYNC_EXPERIMENTS_STARTED, SYNC_EXPERIMENTS_SUCCESS, SYNC_EXPERIMENTS_ERROR
from .models import ExperimentsSyncRequest

logger = get_logger(__name__)

# Wall-clock budget for the entire rsync subprocess. Comfortably above the 15 s
# SSH ConnectTimeout so a slow-but-progressing transfer is not killed, while
# still bounding a stalled session so the UI is told within a reasonable window.
RSYNC_TIMEOUT_S = 120

# rsync exit code 255 == SSH transport failure. The patterns below classify the
# stderr tail into a user-actionable title.
_AUTH_FAIL_PATTERN = re.compile(r"permission denied", re.IGNORECASE)
_UNREACHABLE_PATTERN = re.compile(
    r"connection timed out|connection refused|no route to host|"
    r"could not resolve hostname|network is unreachable",
    re.IGNORECASE,
)


def _classify_rsync_stderr(returncode: int, stderr_tail: str) -> tuple[str, str]:
    """Map an rsync failure into a user-facing (title, text) pair.

    The frontend's error dialog renders the title prominently and the text
    below it, so the title is what the user reads first.
    """
    if _AUTH_FAIL_PATTERN.search(stderr_tail):
        return (
            "SSH authentication failed",
            "The remote host rejected the SSH key. Re-upload your public "
            "key via the SSH Key Portal, or verify the Key Name preference "
            "matches a key the remote host trusts.\n\n" + stderr_tail,
        )
    if _UNREACHABLE_PATTERN.search(stderr_tail):
        return (
            "Could not reach remote host",
            "The remote host did not accept the SSH connection. Check that "
            "the host is online, the IP/hostname is correct, and the SSH "
            "port is reachable.\n\n" + stderr_tail,
        )
    return (f"rsync exit {returncode}", stderr_tail)


# Bound for the pre-flight TCP probe. Short — we only want a quick "is the
# SSH port open" check; the full SSH handshake budget belongs to rsync.
SSH_REACHABILITY_TIMEOUT_S = 3.0


def _ssh_port_reachable(host: str, port: int,
                        timeout_s: float = SSH_REACHABILITY_TIMEOUT_S) -> tuple[bool, str]:
    """Return (reachable, error_text).

    Opens a TCP connection to ``host:port`` and closes it. Tests the SSH
    service is listening and accepting connections, which is more accurate
    than ICMP and works without admin privileges. ``error_text`` is empty
    on success and a short human-readable string on failure (suitable for
    the frontend error dialog).
    """
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True, ""
    except socket.gaierror as e:
        return False, f"Could not resolve hostname {host!r}: {e}"
    except socket.timeout:
        return False, (
            f"Timed out after {timeout_s:.0f}s waiting for {host}:{port} to accept "
            "a TCP connection."
        )
    except OSError as e:
        return False, f"{host}:{port} refused or unreachable: {e}"


@provides(IDramatiqControllerBase)
class SSHService(HasTraits):

    ###################################################################################
    # IDramatiqControllerBase Interface
    ###################################################################################

    dramatiq_listener_actor = Instance(dramatiq.Actor)
    name = listener_name

    def traits_init(self):
        logger.info("Starting SSH controls listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=listener_name,
            class_method=self.listener_actor_routine)

    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(self, message, topic, handler_name_pattern="_on_{topic}_request")


    def _on_generate_keypair_request(self, message):
        message_data = json.loads(message)
        key_name = message_data.get("key_name")
        ssh_dir = message_data.get("ssh_dir")

        err_title = None
        err_msg = None
        
        try:
            with warnings.catch_warnings(record=True) as captured_warnings:
                pub_key_data, priv_key_path, pub_key_path = paramiko_helpers.generate_ssh_keypair(key_name, ssh_dir)

                output = dict()
                output["pub_key_data"] = pub_key_data
                output["priv_key_path"] = priv_key_path
                output["pub_key_path"] = pub_key_path

                publish_message(json.dumps(output), SSH_KEYGEN_SUCCESS)

                if captured_warnings:
                    message = {
                        "title": "User Warning",
                        "text": str(captured_warnings[0].message),
                    }
                    publish_message(json.dumps(message), SSH_KEYGEN_WARNING)

        except FileNotFoundError as e:
            err_title = "FileNotFoundError: Public key exists, but private key is missing"
            err_msg = str(e)

        except OSError as e:
            err_title = "OSError: Failed to read/write public key"
            err_msg = str(e)

        except ValueError as e:  # Catch invalid key names, etc.
            err_title = "Bad Key name"
            err_msg = str(e)

        except Exception as e:
            err_title = "Exception: Failed to generate public key"
            err_msg = str(e)

        finally:
            if err_msg:
                message = {"title": err_title, "text": err_msg}
                publish_message(json.dumps(message), SSH_KEYGEN_ERROR)

    def _on_key_upload_request(self, config):
        """
        Uploads the public key to the server using password auth.
        'config' is a dict from the ViewModel's model.
        """
        config = json.loads(config)
        pub_key = config.get("generated_pub_key")
        if not pub_key:
            publish_message("No key has been generated or read yet.")
            return

        if not all([config["host"], config["port"], config["username"], config["password"]]):
            publish_message("All connection fields are required.", SSH_KEY_UPLOAD_ERROR)
            return

        ssh_client = None
        try:
            # Use the helper function to connect
            ssh_client = paramiko_helpers.get_password_authenticated_client(
                host=config["host"],
                port=config["port"],
                username=config["username"],
                password=config['password']
            )

            # Use the helper function to upload
            exit_status = paramiko_helpers.upload_public_key(ssh_client, pub_key)

            if exit_status == 0:
                publish_message(
                    f"Public key authorized on {config['host']}.\nYou can now try connecting with your private key.",
                    SSH_KEY_UPLOAD_SUCCESS)
            else:
                publish_message("The server failed to add the key. Check permissions or see server logs.", SSH_KEY_UPLOAD_ERROR)

        except AuthenticationException:
            publish_message("Authentication Failed. Please check your username and password.", SSH_KEY_UPLOAD_ERROR)

        except Exception as e:
            publish_message(f"An unexpected error occurred: {e}", SSH_KEY_UPLOAD_ERROR)

        finally:
            if ssh_client:
                ssh_client.close()

    def _on_sync_experiments_request(self, message):
        """Handler for ``ssh_service/request/sync_experiments``.

        Runs rsync over SSH as the local (frontend) host, pulling from
        the remote backend. Publishes a ``started`` ack on receipt and
        either ``success`` or ``error`` when the blocking rsync call
        completes. Blocks this dramatiq worker for the duration of the
        transfer (consistent with _on_key_upload_request).
        """
        try:
            model = ExperimentsSyncRequest.model_validate_json(message)
        except ValidationError as e:
            logger.error(e, exc_info=True)
            publish_message(
                json.dumps({"title": "Invalid sync request", "text": str(e)}),
                SYNC_EXPERIMENTS_ERROR,
            )
            return

        # Pre-flight: TCP-connect to the SSH port. Fails in a few seconds when
        # the host is offline / wrong IP / wrong port, instead of waiting on
        # rsync's 15s ConnectTimeout. Auth failures still surface from rsync.
        reachable, reach_err = _ssh_port_reachable(model.host, model.port)
        if not reachable:
            logger.error(
                "SSH host %s:%s unreachable before sync: %s",
                model.host, model.port, reach_err,
            )
            publish_message(
                json.dumps({
                    "title": "Could not reach remote host",
                    "text": reach_err,
                }),
                SYNC_EXPERIMENTS_ERROR,
            )
            return

        publish_message(
            json.dumps({"message": "Sync started"}),
            SYNC_EXPERIMENTS_STARTED,
        )

        try:
            result = Rsync().sync(
                src=model.src,
                dest=model.dest,
                identity=model.identity_path,
                ssh_port=model.port,
                archive=True,
                partial=True,
                verbose=True,
                capture_output=True,
                check=False,
                timeout=RSYNC_TIMEOUT_S,
            )
            if result.returncode != 0 or result.stderr:
                tail = (result.stderr or "")[-500:]
                logger.error(f"Rsync Exit: {result.returncode}; {tail}")

                if tail not in SYNC_EXCEPTIONS_TO_PASS:
                    title, text = _classify_rsync_stderr(result.returncode, tail)
                    publish_message(
                        json.dumps({"title": title, "text": text}),
                        SYNC_EXPERIMENTS_ERROR,
                    )
                    return

                else:
                    logger.warning(f"This Exception is set to be ignored: {tail}")


            logger.info("Sync succeeded")
            publish_message(
                json.dumps({"message": "Sync complete."}),
                SYNC_EXPERIMENTS_SUCCESS,
            )

        except subprocess.TimeoutExpired:
            logger.error("Remote sync timed out after %s s", RSYNC_TIMEOUT_S)
            publish_message(
                json.dumps({
                    "title": "Connection timed out",
                    "text": (
                        f"Could not reach {model.username}@{model.host}:{model.port} "
                        f"within {RSYNC_TIMEOUT_S}s. Check that the host is online "
                        "and the SSH port is correct."
                    ),
                }),
                SYNC_EXPERIMENTS_ERROR,
            )
        except FileNotFoundError as e:
            logger.error(e, exc_info=True)
            publish_message(
                json.dumps({"title": "rsync executable not found", "text": str(e)}),
                SYNC_EXPERIMENTS_ERROR,
            )
        except Exception as e:
            logger.error("Remote sync failed")
            publish_message(
                json.dumps({"title": "Unexpected error", "text": str(e)}),
                SYNC_EXPERIMENTS_ERROR,
            )
