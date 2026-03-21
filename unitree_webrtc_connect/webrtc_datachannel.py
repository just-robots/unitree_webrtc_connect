from __future__ import annotations
import asyncio
import json
import struct
import logging
from unitree_webrtc_connect.msgs.pub_sub import WebRTCDataChannelPubSub
from unitree_webrtc_connect.lidar.lidar_decoder_native import LidarDecoder
from unitree_webrtc_connect.msgs.heartbeat import WebRTCDataChannelHeartBeat
from unitree_webrtc_connect.msgs.validation import WebRTCDataChannelValidaton
from unitree_webrtc_connect.msgs.rtc_inner_req import WebRTCDataChannelRTCInnerReq
from unitree_webrtc_connect.msgs.error_handler import handle_error

from unitree_webrtc_connect.constants import DATA_CHANNEL_TYPE

from typing import Any
from aiortc import RTCPeerConnection

logger = logging.getLogger(__name__)


class WebRTCDataChannel:
    def __init__(self, conn: Any, pc: RTCPeerConnection) -> None:
        self.channel = pc.createDataChannel("data")
        self.data_channel_opened = False
        self.conn = conn

        self.pub_sub = WebRTCDataChannelPubSub(self.channel)

        self.heartbeat = WebRTCDataChannelHeartBeat(self.channel, self.pub_sub)
        self.validaton = WebRTCDataChannelValidaton(self.channel, self.pub_sub)
        self.rtc_inner_req = WebRTCDataChannelRTCInnerReq(self.conn, self.channel, self.pub_sub)

        self.set_decoder(decoder_type="libvoxel")

        # Event handler for Validation succeed
        def on_validate():
            self.data_channel_opened = True
            self.heartbeat.start_heartbeat()
            self.rtc_inner_req.network_status.start_network_status_fetch()
            logger.info("Data Channel Verification: ✅ OK")

        self.validaton.set_on_validate_callback(on_validate)

        # Event handler for Network status Update
        def on_network_status(mode: Any):
            logger.info(f"Go2 connection mode: {mode}")

        self.rtc_inner_req.network_status.set_on_network_status_callback(on_network_status)

        # Event handler for data channel open
        @self.channel.on("open")
        def on_open():
            logger.info("Data channel opened")

        # Event handler for data channel close
        @self.channel.on("close")
        def on_close():
            logger.info("Data channel closed")
            self.data_channel_opened = False
            self.heartbeat.stop_heartbeat()
            self.rtc_inner_req.network_status.stop_network_status_fetch()

        # Event handler for data channel messages
        @self.channel.on("message")
        async def on_message(message: str | bytes | Any):
            logger.info("Received message on data channel: %s", message)
            try:
                # Check if the message is not empty
                if not message:
                    return

                # Determine how to parse the 'data' field
                if isinstance(message, str):
                    parsed_data: dict[str, Any] = json.loads(message)
                elif isinstance(message, bytes):
                    parsed_data = self.deal_array_buffer(message)
                else:
                    logger.error("Invalid message type: %s", type(message))
                    return

                # Resolve any pending futures or callbacks associated with this message
                self.pub_sub.run_resolve(parsed_data)

                # Handle the response
                await self.handle_response(parsed_data)

            except json.JSONDecodeError:
                logger.exception("Failed to decode JSON message: %s", message)
            except Exception:
                logger.exception("Error processing WebRTC data")

    async def handle_response(self, msg: dict):
        msg_type = msg["type"]

        if msg_type == DATA_CHANNEL_TYPE["VALIDATION"]:
            await self.validaton.handle_response(msg)
        elif msg_type == DATA_CHANNEL_TYPE["RTC_INNER_REQ"]:
            self.rtc_inner_req.handle_response(msg)
        elif msg_type == DATA_CHANNEL_TYPE["HEARTBEAT"]:
            self.heartbeat.handle_response(msg)
        elif msg_type in {
            DATA_CHANNEL_TYPE["ERRORS"],
            DATA_CHANNEL_TYPE["ADD_ERROR"],
            DATA_CHANNEL_TYPE["RM_ERROR"],
        }:
            handle_error(msg)
        elif msg_type == DATA_CHANNEL_TYPE["ERR"]:
            await self.validaton.handle_err_response(msg)

    async def wait_datachannel_open(self, timeout: float = 5) -> None:
        """Waits for the data channel to open asynchronously."""
        try:
            await asyncio.wait_for(self._wait_for_open(), timeout)
        except asyncio.TimeoutError as e:
            logger.warning("Data channel did not open in time")
            raise RuntimeError("Data channel did not open in time") from e

    async def _wait_for_open(self):
        """Internal function that waits for the data channel to be opened."""
        while not self.data_channel_opened:  # noqa: ASYNC110
            await asyncio.sleep(0.1)

    def deal_array_buffer(self, buffer: bytes) -> dict[str, Any]:
        header_1, header_2 = struct.unpack_from("<HH", buffer, 0)
        if header_1 == 2 and header_2 == 0:
            return self.deal_array_buffer_for_lidar(buffer[4:])
        return self.deal_array_buffer_for_normal(buffer)

    def deal_array_buffer_for_normal(self, buffer: bytes) -> dict[str, Any]:
        (header_length,) = struct.unpack_from("<H", buffer, 0)
        json_data = buffer[4 : 4 + header_length]
        binary_data = buffer[4 + header_length :]

        decoded_json = json.loads(json_data.decode("utf-8"))

        decoded_data = self.decoder.decode(binary_data, decoded_json["data"])

        decoded_json["data"]["data"] = decoded_data
        return decoded_json

    def deal_array_buffer_for_lidar(self, buffer: bytes) -> dict[str, Any]:
        (header_length,) = struct.unpack_from("<I", buffer, 0)
        json_data = buffer[8 : 8 + header_length]
        binary_data = buffer[8 + header_length :]

        decoded_json = json.loads(json_data.decode("utf-8"))

        decoded_data = self.decoder.decode(binary_data, decoded_json["data"])

        decoded_json["data"]["data"] = decoded_data
        return decoded_json

    # Should turn it on when subscribed to ulidar topic
    async def disable_traffic_aving(self, switch: bool) -> bool:
        data = {"req_type": "disable_traffic_saving", "instruction": "on" if switch else "off"}
        response = await self.pub_sub.publish(
            "",
            data,
            DATA_CHANNEL_TYPE["RTC_INNER_REQ"],
        )
        if response["info"]["execution"] == "ok":
            logger.info(f"DisableTrafficSavings: {data['instruction']}")
            return True
        return False

    # Enable/Disable video channel
    def switch_video_channel(self, switch: bool) -> None:
        self.pub_sub.publish_without_callback(
            "",
            "on" if switch else "off",
            DATA_CHANNEL_TYPE["VID"],
        )
        logger.info(f"Video channel: {'on' if switch else 'off'}")

    # Enable/Disable audio channel
    def switch_audio_channel(self, switch: bool) -> None:
        self.pub_sub.publish_without_callback(
            "",
            "on" if switch else "off",
            DATA_CHANNEL_TYPE["AUD"],
        )
        logger.info(f"Audio channel: {'on' if switch else 'off'}")

    def set_decoder(self, decoder_type: str) -> None:
        """
        Set the decoder to be used for decoding incoming data.

        :param decoder_type: The type of decoder to use ("libvoxel" or "native").
        """
        _ = decoder_type
        self.decoder = LidarDecoder()
