import hashlib
import json
import random
import requests
from typing import Any
import logging
from Crypto.PublicKey import RSA
from unitree_webrtc_connect.unitree_auth import make_remote_request
from unitree_webrtc_connect.encryption import (
    rsa_encrypt,
    rsa_load_public_key,
    aes_decrypt,
    generate_aes_key,
)


logger = logging.getLogger(__name__)


# Function to generate MD5 hash of a string


def _generate_md5(string: str) -> str:
    md5_hash = hashlib.md5(string.encode())  # noqa: S324
    return md5_hash.hexdigest()


def generate_uuid():
    def replace_char(char: str) -> str:
        rand = random.randint(0, 15)  # noqa: S311
        if char == "x":
            return format(rand, "x")
        if char == "y":
            return format((rand & 0x3) | 0x8, "x")
        return char

    uuid_template = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx"
    return "".join(replace_char(char) for char in uuid_template)


def get_nested_field(message: dict[str, Any], *fields: str) -> Any:
    current_level = message
    for field in fields:
        if isinstance(current_level, dict) and field in current_level:
            current_level = current_level[field]
        else:
            return None
    return current_level


# Function to obtain a fresh token from the backend server
def fetch_token(email: str, password: str) -> str:
    logger.info("Obtaining TOKEN...")
    path = "login/email"
    body = {"email": email, "password": _generate_md5(password)}
    response = make_remote_request(path, body, token="", method="POST")
    if response.get("code") == 100:
        data = response.get("data")
        if data is None:
            raise ValueError("No data received from the server")
        access_token = data.get("accessToken")
        return access_token

    raise ValueError("failed to receive token")


# Function to obtain a public key
def fetch_public_key() -> RSA.RsaKey:
    logger.info("Obtaining a Public key...")
    path = "system/pubKey"

    try:
        # Attempt to make the request
        response = make_remote_request(path, {}, token="", method="GET")

        if response.get("code") == 100:
            public_key_pem = response.get("data")
            if public_key_pem is None:
                raise ValueError("No public key received from the server")

            return rsa_load_public_key(public_key_pem)

        raise ValueError("Failed to receive public key")
        return None

    except requests.exceptions.ConnectionError:
        # Handle no internet connection or other connection errors
        logger.warning(
            "No internet connection or failed to connect to the server. Unable to fetch public key."
        )
        raise
    except requests.exceptions.RequestException as e:
        # Handle other request exceptions
        raise RuntimeError(f"An error occurred while fetching the public key: {e}") from e


# Function to obtain TURN server info
def fetch_turn_server_info(
    serial: str, access_token: str, public_key: RSA.RsaKey
) -> dict[str, Any] | None:
    logger.info("Obtaining TURN server info...")
    aes_key = generate_aes_key()
    path = "webrtc/account"
    body = {"sn": serial, "sk": rsa_encrypt(aes_key, public_key)}
    response = make_remote_request(path, body, token=access_token, method="POST")
    if response.get("code") == 100:
        return json.loads(aes_decrypt(response["data"], aes_key))

    raise ValueError("Failed to receive TURN server info")
