from unitree_webrtc_connect.webrtc_datachannel import WebRTCDataChannel
from aiortc import RTCPeerConnection, MediaStreamTrack
from collections.abc import Callable
from typing import Any
import logging

logger = logging.getLogger(__name__)


class WebRTCVideoChannel:
    def __init__(self, pc: RTCPeerConnection, datachannel: WebRTCDataChannel) -> None:
        self.pc = pc
        self.pc.addTransceiver("video", direction="recvonly")
        self.datachannel = datachannel
        # List to hold multiple callbacks
        self.track_callbacks: list[Callable[[MediaStreamTrack], Any]] = []

    def switch_video_channel(self, switch: bool):
        self.datachannel.switch_video_channel(switch)

    def add_track_callback(self, callback: Callable[[MediaStreamTrack], Any]):
        """
        Adds a callback to be triggered when an audio track is received.
        """
        self.track_callbacks.append(callback)

    async def track_handler(self, track: MediaStreamTrack):
        logger.info("Receiving video frame")
        # Trigger all registered callbacks
        for callback in self.track_callbacks:
            try:
                # Call each callback function and pass the track
                await callback(track)
            except Exception:
                logger.exception(f"Error in callback {callback}")
