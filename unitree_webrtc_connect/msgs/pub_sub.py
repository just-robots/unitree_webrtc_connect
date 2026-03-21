import asyncio
import json
import time
import random
from collections.abc import Callable
from aiortc import RTCDataChannel
from unitree_webrtc_connect.constants import DATA_CHANNEL_TYPE
from unitree_webrtc_connect.msgs.future_resolver import FutureResolver
from unitree_webrtc_connect.util import get_nested_field
from typing import Any
import logging

logger = logging.getLogger(__name__)


class WebRTCDataChannelPubSub:
    def __init__(self, channel: RTCDataChannel):
        self.channel = channel

        self.future_resolver = FutureResolver()
        self.subscriptions = {}  # Dictionary to hold callbacks keyed by topic

    def run_resolve(self, message: dict[str, Any]):
        self.future_resolver.run_resolve_for_topic(message)

        # Extract the topic from the message
        topic = message.get("topic")
        if topic in self.subscriptions:
            # Call the registered callback with the message
            callback = self.subscriptions[topic]
            callback(message)

    async def publish(
        self, topic: str, data: dict[str, Any] | str | None = None, msg_type: str | None = None
    ):
        channel = self.channel
        future = asyncio.get_event_loop().create_future()

        if channel.readyState == "open":
            message_dict: dict[str, Any] = {
                "type": msg_type or DATA_CHANNEL_TYPE["MSG"],
                "topic": topic,
            }
            # Only include "data" if it's not None
            if data is not None:
                message_dict["data"] = data

            # Convert the dictionary to a JSON string
            message = json.dumps(message_dict)

            channel.send(message)

            # Log the message being published
            logger.info(f"> message sent: {message}")

            # Store the future so it can be completed when the response is received
            uuid = None
            if isinstance(data, dict):
                uuid = str(
                    get_nested_field(data, "uuid")
                    or get_nested_field(data, "header", "identity", "id")
                    or get_nested_field(data, "req_uuid")
                )

            self.future_resolver.save_resolve(
                msg_type or DATA_CHANNEL_TYPE["MSG"], topic, future, uuid
            )
        else:
            logger.error("Data channel is not open")
            future.set_exception(Exception("Data channel is not open"))

        return await future

    def publish_without_callback(
        self, topic: str, data: dict[str, Any] | str | None = None, msg_type: str | None = None
    ):

        if self.channel.readyState == "open":
            message_dict: dict[str, Any] = {
                "type": msg_type or DATA_CHANNEL_TYPE["MSG"],
                "topic": topic,
            }

            # Only include "data" if it's not None
            if data is not None:
                message_dict["data"] = data

            # Convert the dictionary to a JSON string
            message = json.dumps(message_dict)

            self.channel.send(message)

            # Log the message being published
            logger.info(f"> message sent: {message}")
        else:
            raise RuntimeError("Data channel is not open")

    async def publish_request_new(
        self, topic: str, options: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        # Generate a unique identifier
        generated_id = int(time.time() * 1000) % 2147483648 + random.randint(0, 1000)  # noqa: S311

        # Check if api_id is provided
        if not (options and "api_id" in options):
            logger.error("Error: Please provide app id")
            fut = asyncio.Future()
            fut.set_exception(Exception("Please provide app id"))
            return await fut

        # Build the request header and parameter
        request_payload = {
            "header": {
                "identity": {
                    "id": options.get("id", generated_id),
                    "api_id": options.get("api_id", 0),
                }
            },
            "parameter": "",
        }

        # Add data to parameter
        if options and "parameter" in options:
            request_payload["parameter"] = (
                options["parameter"]
                if isinstance(options["parameter"], str)
                else json.dumps(options["parameter"])
            )

        # Add priority if specified
        if options and "priority" in options:
            request_payload["header"]["policy"] = {"priority": 1}

        # Publish the request
        return await self.publish(topic, request_payload, DATA_CHANNEL_TYPE["REQUEST"])

    def subscribe(self, topic: str, callback: Callable[[dict[str, Any]], None] | None = None):
        channel = self.channel

        if not channel or channel.readyState != "open":
            raise RuntimeError("Data channel is not open, cannot subscribe")

        # Register the callback for the topic
        if callback:
            self.subscriptions[topic] = callback

        self.publish_without_callback(topic=topic, msg_type=DATA_CHANNEL_TYPE["SUBSCRIBE"])

    def unsubscribe(self, topic: str):
        channel = self.channel

        if not channel or channel.readyState != "open":
            raise RuntimeError("Data channel is not open, cannot unsubscribe")

        self.publish_without_callback(topic=topic, msg_type=DATA_CHANNEL_TYPE["UNSUBSCRIBE"])
