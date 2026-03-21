import logging
import base64
from unitree_webrtc_connect.constants import DATA_CHANNEL_TYPE
from aiortc import RTCDataChannel
from unitree_webrtc_connect.msgs.pub_sub import WebRTCDataChannelPubSub

from typing import Any
from collections.abc import Callable
import logging
import hashlib

logger = logging.getLogger(__name__)


class WebRTCDataChannelValidaton:
    def __init__(self, channel: RTCDataChannel, pub_sub: WebRTCDataChannelPubSub):
        self.channel = channel
        self.publish = pub_sub.publish
        self.on_validate_callbacks = []
        self.key = ""

    def set_on_validate_callback(self, callback: Callable[[], None]):
        """Register a callback to be called upon validation."""
        self.on_validate_callbacks.append(callback)

    async def handle_response(self, message: dict[str, Any]):
        if message.get("data") == "Validation Ok.":
            logger.info("Validation succeed")
            for callback in self.on_validate_callbacks:
                callback()
        else:
            self.channel._setReadyState("open")  # noqa: SLF001
            self.key = str(message.get("data"))
            await self.publish(
                "",
                self.encrypt_key(self.key),
                DATA_CHANNEL_TYPE["VALIDATION"],
            )

    async def handle_err_response(self, message: dict[str, Any]):
        if message.get("info") == "Validation Needed.":
            await self.publish(
                "",
                self.encrypt_key(self.key),
                DATA_CHANNEL_TYPE["VALIDATION"],
            )

    @staticmethod
    def hex_to_base64(hex_str: str) -> str:
        # Convert hex string to bytes
        bytes_array = bytes.fromhex(hex_str)
        # Encode the bytes to Base64 and return as a string
        return base64.b64encode(bytes_array).decode("utf-8")

    @staticmethod
    def encrypt_by_md5(input_str: str) -> str:

        # Create an MD5 hash object
        hash_obj = hashlib.md5()  # noqa: S324
        # Update the hash object with the bytes of the input string
        hash_obj.update(input_str.encode("utf-8"))
        # Return the hex digest of the hash
        return hash_obj.hexdigest()

    @staticmethod
    def encrypt_key(key: str) -> str:
        # Append the prefix to the key
        prefixed_key = f"UnitreeGo2_{key}"
        # Encrypt the key using MD5 and convert to hex string
        encrypted = WebRTCDataChannelValidaton.encrypt_by_md5(prefixed_key)
        # Convert the hex string to Base64
        return WebRTCDataChannelValidaton.hex_to_base64(encrypted)
