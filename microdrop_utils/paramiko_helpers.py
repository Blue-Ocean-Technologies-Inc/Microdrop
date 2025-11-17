import os
import paramiko
from typing import Tuple


def generate_ssh_keypair(key_name: str, ssh_dir: str) -> Tuple[str, str, str]:
    """
    Generates a new RSA key pair and saves it to disk.

    Args:
        key_name: The desired name for the key file (e.g., "id_rsa_new").
        ssh_dir: The directory to save the keys in (e.g., "~/.ssh").

    Returns:
        A tuple of (public_key_string, private_key_path, public_key_path).

    Raises:
        ValueError: If key_name is empty.
        FileExistsError: If the key files already exist.
        OSError: If there's an issue creating directories or files.
        paramiko.SSHException: If key generation fails.
    """
    if not key_name:
        raise ValueError("Key name cannot be empty.")

    os.makedirs(ssh_dir, exist_ok=True)

    priv_key_path = os.path.join(ssh_dir, key_name)
    pub_key_path = f"{priv_key_path}.pub"

    if os.path.exists(priv_key_path) or os.path.exists(pub_key_path):
        raise FileExistsError(f"Files already exist at {priv_key_path}")

    # Generate the key
    key = paramiko.RSAKey.generate(4096)

    # Save private key
    key.write_private_key_file(priv_key_path)
    os.chmod(priv_key_path, 0o600)  # Set secure permissions

    # Save public key
    pub_key_data = f"{key.get_name()} {key.get_base64()}"
    with open(pub_key_path, "w") as f:
        f.write(pub_key_data)

    return (pub_key_data, priv_key_path, pub_key_path)


def get_password_authenticated_client(host: str, port: int, username: str, password: str) -> paramiko.SSHClient:
    """
    Creates and returns a password-authenticated paramiko.SSHClient.

    Args:
        host: The server hostname or IP.
        port: The SSH port.
        username: The username.
        password: The password.

    Returns:
        A connected paramiko.SSHClient instance.

    Raises:
        paramiko.AuthenticationException
        paramiko.SSHException
        socket.error
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=port,
        username=username,
        password=password,
        timeout=10
    )
    return client


def upload_public_key(client: paramiko.SSHClient, pub_key: str) -> int:
    """
    Uploads a public key string to the server's authorized_keys file.

    Args:
        client: A *connected* paramiko.SSHClient instance.
        pub_key: The public key string (e.g., "ssh-rsa AAAA...").

    Returns:
        The exit status code from the remote command.
    """
    cmd = (
        f'mkdir -p ~/.ssh && '
        f'chmod 700 ~/.ssh && '
        f'touch ~/.ssh/authorized_keys && '
        f'chmod 600 ~/.ssh/authorized_keys && '
        f'grep -q -F "{pub_key}" ~/.ssh/authorized_keys || '
        f'echo "{pub_key}" >> ~/.ssh/authorized_keys'
    )

    _stdin, _stdout, stderr = client.exec_command(cmd)
    exit_status = _stdout.channel.recv_exit_status()

    if exit_status != 0:
        # For debugging, one could log stderr.read().decode()
        pass

    return exit_status