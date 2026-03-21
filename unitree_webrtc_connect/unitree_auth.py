import hashlib
import time
import requests
import urllib.parse
import base64
import json
from typing import Any
from Crypto.PublicKey import RSA
from unitree_webrtc_connect.encryption import (
    aes_encrypt,
    generate_aes_key,
    rsa_encrypt,
    aes_decrypt,
    rsa_load_public_key,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import logging

logger = logging.getLogger(__name__)

APP_SIGN_SECRET = "XyvkwK45hp5PHfA8"  # noqa: S105
UM_CHANNEL_KEY = "UMENG_CHANNEL"
BASE_URL = "https://global-robot-api.unitree.com/"
REQ_TIMEOUT_SECS = 10


def decrypt_con_notify_data(encrypted_b64: str) -> str:
    key = bytes([232, 86, 130, 189, 22, 84, 155, 0, 142, 4, 166, 104, 43, 179, 235, 227])

    data = base64.b64decode(encrypted_b64)

    if len(data) < 28:
        raise ValueError("Decryption failed: input data too short")

    tag = data[-16:]
    nonce = data[-28:-16]
    ciphertext = data[:-28]

    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext + tag, None)
    return plaintext.decode("utf-8")


def _calc_local_path_ending(data1: str):
    # Initialize an array of strings
    str_array = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]

    # Extract the last 10 characters of data1
    last_10_chars = data1[-10:]

    # Split the last 10 characters into chunks of size 2
    chunked = [last_10_chars[i : i + 2] for i in range(0, len(last_10_chars), 2)]

    # Initialize an empty list to store indices
    array_list: list[int] = []

    # Iterate over the chunks and find the index of the second character in strArr
    for chunk in chunked:
        if len(chunk) > 1:
            second_char = chunk[1]
            try:
                index = str_array.index(second_char)
                array_list.append(index)
            except ValueError:
                # Handle case where the character is not found in strArr
                logger.info(f"Character {second_char} not found in strArr.")

    # Convert arrayList to a string without separators
    join_to_string = "".join(map(str, array_list))

    return join_to_string


def make_remote_request(
    path: str, body: dict[str, Any], token: str, method: str = "GET"
) -> dict[str, Any]:
    # Constants

    # Current timestamp and nonce
    app_timestamp = str(round(time.time() * 1000))
    app_nonce = hashlib.md5(app_timestamp.encode()).hexdigest()  # noqa: S324

    # Generating app sign
    sign_str = f"{APP_SIGN_SECRET}{app_timestamp}{app_nonce}"
    app_sign = hashlib.md5(sign_str.encode()).hexdigest()  # noqa: S324

    # Get system's timezone offset in seconds and convert it to hours and minutes
    timezone_offset = time.localtime().tm_gmtoff // 3600
    minutes_offset = abs(time.localtime().tm_gmtoff % 3600 // 60)
    sign = "+" if timezone_offset >= 0 else "-"
    app_timezone = f"GMT{sign}{abs(timezone_offset):02d}:{minutes_offset:02d}"

    # Headers
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "DeviceId": "Samsung/GalaxyS20/SM-G981B/s20/10/29",
        "AppTimezone": app_timezone,
        "DevicePlatform": "Android",
        "DeviceModel": "SM-G981B",
        "SystemVersion": "29",
        "AppVersion": "1.8.0",
        "AppLocale": "en_US",
        "AppTimestamp": app_timestamp,
        "AppNonce": app_nonce,
        "AppSign": app_sign,
        "Channel": UM_CHANNEL_KEY,
        "Token": token,
        "AppName": "Go2",
        "Host": "global-robot-api.unitree.com",
        "User-Agent": "Mozilla/5.0 (Linux; Android 15; SM-S931B Build/AP3A.240905.015.A2; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/127.0.6533.103 Mobile Safari/537.36",
    }

    # Full URL
    url = BASE_URL + path

    if method.upper() == "GET":
        # Convert body dictionary to query parameters for GET request
        params = urllib.parse.urlencode(body)
        response = requests.get(url, params=params, headers=headers, timeout=REQ_TIMEOUT_SECS)
    else:
        # URL-encode the body for POST request
        encoded_body = urllib.parse.urlencode(body)
        response = requests.post(url, data=encoded_body, headers=headers, timeout=REQ_TIMEOUT_SECS)

    # Return the response as JSON
    return response.json()


def make_local_request(
    path: str, body: str | dict[str, None] | None = None, headers: dict[str, Any] | None = None
) -> requests.Response | None:
    try:
        # Send POST request with provided path, body, and headers
        response = requests.post(url=path, data=body, headers=headers, timeout=REQ_TIMEOUT_SECS)

        # Check if the request was successful (status code 200)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx, 5xx)

        if response.status_code == 200:
            return response  # Returning the whole response object if needed

        return None

    except requests.exceptions.RequestException:
        # Handle any exception related to the request (e.g., connection errors, timeouts)
        logger.exception(f"An error occurred while making a local request to {path}")
        return None


# Function to send SDP to peer and receive the answer
def send_sdp_to_remote_peer(
    serial: str | None, sdp: str, access_token: str, public_key: RSA.RsaKey
) -> str:
    logger.info("Sending SDP to Go2...")
    aes_key = generate_aes_key()
    path = "webrtc/connect"
    body = {
        "sn": serial,
        "sk": rsa_encrypt(aes_key, public_key),
        "data": aes_encrypt(sdp, aes_key),
        "timeout": 5,
    }
    response = make_remote_request(path, body, token=access_token, method="POST")
    if response.get("code") == 100:
        logger.info("Received SDP Answer from Go2!")
        return aes_decrypt(response["data"], aes_key)

    if response.get("code") == 1000:
        raise RuntimeError("Device not online")

    raise ValueError(f"Failed to receive SDP Answer: {response}")


def send_sdp_to_local_peer(ip: str, sdp: str):
    try:
        # Try the old method first
        logger.info("Trying to send SDP using the old method...")
        response = send_sdp_to_local_peer_old_method(ip, sdp)
        if response:
            logger.info("SDP successfully sent using the old method.")
            return response
        logger.warning("Old method failed, trying the new method...")
    except Exception:
        logger.exception(f"An error occurred with the old method")
        logger.info("Falling back to the new method...")

    # Now try the new method after the old method has failed
    try:
        response = send_sdp_to_local_peer_new_method(ip, sdp)  # Use the new method here
        if response:
            logger.info("SDP successfully sent using the new method.")
            return response
        logger.error("New method failed to send SDP.")
        return None
    except Exception:
        logger.exception(f"An error occurred with the new method")
        return None


def send_sdp_to_local_peer_old_method(ip: str, sdp: str) -> str | None:
    """
    Sends an SDP message to a local peer using an HTTP POST request.

    Args:
        ip (str): The IP address of the local peer to send the SDP message.
        sdp (dict): The SDP message to be sent in the request body.

    Returns:
        response: The response from the local peer if the request is successful, otherwise None.
    """
    try:
        # Define the URL for the POST request
        url = f"http://{ip}:8081/offer"

        # Define headers for the POST request
        headers = {"Content-Type": "application/json"}

        # Send the POST request with the SDP body (convert the dict to JSON)
        response = make_local_request(url, body=sdp, headers=headers)

        # Check if the response is valid
        if response and response.status_code == 200:
            logger.debug(f"Recieved SDP: {response.text}")
            return response.text

        raise ValueError(
            f"Failed to receive SDP Answer: {response.status_code if response else 'No response'}"
        )

    except requests.exceptions.RequestException:
        # Handle any exceptions that occur during the request
        logger.exception(f"An error occurred while sending the SDP")
        return None


def send_sdp_to_local_peer_new_method(ip: str, sdp: str) -> str | None:
    try:
        url = f"http://{ip}:9991/con_notify"

        # Initial request to get public key information
        response = make_local_request(url, body=None, headers=None)

        # Check if the response status code is 200 (OK)
        if response:
            # Decode the response text from base64
            decoded_response = base64.b64decode(response.text).decode("utf-8")
            logger.debug(f"Recieved con_notify response: {decoded_response}")

            # Parse the decoded response as JSON
            decoded_json = json.loads(decoded_response)

            # Extract the 'data1' field from the JSON
            data1 = decoded_json.get("data1")
            data2 = decoded_json.get("data2")

            if data2 == 2:
                data1 = decrypt_con_notify_data(data1)

            # Extract the public key from 'data1'
            public_key_pem = data1[10 : len(data1) - 10]
            path_ending = _calc_local_path_ending(data1)

            # Generate AES key
            aes_key = generate_aes_key()

            # Load Public Key
            public_key = rsa_load_public_key(public_key_pem)

            # Encrypt the SDP and AES key
            body = {
                "data1": aes_encrypt(sdp, aes_key),
                "data2": rsa_encrypt(aes_key, public_key),
            }

            # URL for the second request
            url = f"http://{ip}:9991/con_ing_{path_ending}"

            # Set the appropriate headers for URL-encoded form data
            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            # Send the encrypted data via POST
            response = make_local_request(url, body=json.dumps(body), headers=headers)

            # If response is successful, decrypt it
            if response:
                decrypted_response = aes_decrypt(response.text, aes_key)
                logger.debug(f"Recieved con_ing_{path_ending} response: {decrypted_response}")
                return decrypted_response
        else:
            raise ValueError("Failed to receive initial public key response.")

    except requests.exceptions.RequestException:
        # Handle any exceptions that occur during the request
        logger.exception(f"An error occurred while sending the SDP")
        return None
    except json.JSONDecodeError:
        # Handle JSON decoding errors
        logger.exception(f"An error occurred while decoding JSON")
        return None
    except base64.binascii.Error:  # type: ignore[reportUnknownMemberType]
        # Handle base64 decoding errors
        logger.exception(f"An error occurred while decoding base64")
        return None
