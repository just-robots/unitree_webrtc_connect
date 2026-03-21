from aiortc import RTCPeerConnection
from unitree_webrtc_connect.webrtc_datachannel import WebRTCDataChannel
import logging
from collections.abc import Callable
from typing import Any
from av.frame import Frame
from av.packet import Packet

logger = logging.getLogger(__name__)


class WebRTCAudioChannel:
    def __init__(self, pc: RTCPeerConnection, datachannel: WebRTCDataChannel) -> None:
        self.pc = pc
        self.pc.addTransceiver("audio", direction="sendrecv")
        self.datachannel = datachannel

        # List to hold multiple callbacks
        self.track_callbacks: list[Callable[[Frame | Packet], Any]] = []

    async def frame_handler(self, frame: Frame | Packet):
        logger.info("Receiving audio frame")

        # Trigger all registered callbacks
        for callback in self.track_callbacks:
            try:
                # Call each callback function and pass the track
                await callback(frame)
            except Exception:
                logger.exception(f"Error in callback {callback}")

    def add_track_callback(self, callback: Callable[[Frame | Packet], Any]):
        """
        Adds a callback to be triggered when an audio track is received.
        """
        self.track_callbacks.append(callback)

    def switch_audio_channel(self, switch: bool):
        self.datachannel.switch_audio_channel(switch)
