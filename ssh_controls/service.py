import json
import warnings

import dramatiq
from paramiko import AuthenticationException
from traits.api import HasTraits, provides, Instance

from logger.logger_service import get_logger
from microdrop_utils import paramiko_helpers
from microdrop_utils.dramatiq_controller_base import (
    IDramatiqControllerBase, 
    basic_listener_actor_routine, 
    generate_class_method_dramatiq_listener_actor
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message


from .consts import listener_name, SSH_KEYGEN_SUCCESS, \
    SSH_KEYGEN_WARNING, SSH_KEYGEN_ERROR, SSH_KEY_UPLOAD_ERROR, SSH_KEY_UPLOAD_SUCCESS

logger = get_logger(__name__)


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
