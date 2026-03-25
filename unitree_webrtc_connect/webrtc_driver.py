import json
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCIceServer,
    RTCConfiguration,
    MediaStreamTrack,
)
from unitree_webrtc_connect.unitree_auth import (
    send_sdp_to_local_peer,
    send_sdp_to_remote_peer,
)
import logging
from unitree_webrtc_connect.webrtc_datachannel import WebRTCDataChannel
from unitree_webrtc_connect.webrtc_audio import WebRTCAudioChannel
from unitree_webrtc_connect.webrtc_video import WebRTCVideoChannel
from unitree_webrtc_connect.constants import WebRTCConnectionMethod
from unitree_webrtc_connect.util import (
    fetch_public_key,
    fetch_token,
    fetch_turn_server_info,
)
from unitree_webrtc_connect.multicast_scanner import discover_ip_sn
from typing import Any

logger = logging.getLogger(__name__)


class UnitreeWebRTCConnection:
    def __init__(
        self,
        connection_method: WebRTCConnectionMethod,
        serial_number: str | None = None,
        ip: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.pc = None
        self.sn = serial_number
        self.ip = ip
        self.connectionMethod = connection_method
        self.isConnected = False
        self.token = fetch_token(username, password) if username and password else ""

    async def connect(self):
        logger.info("WebRTC connection: 🟡 started")
        if self.connectionMethod == WebRTCConnectionMethod.Remote:
            self.public_key = fetch_public_key()
            if self.sn is None:
                raise ValueError("Serial number is required for remote connection")
            turn_server_info = fetch_turn_server_info(self.sn, self.token, self.public_key)
            await self.init_webrtc(turn_server_info)
        elif self.connectionMethod == WebRTCConnectionMethod.LocalSTA:
            if not self.ip and self.sn:
                discovered_ip_sn_addresses = discover_ip_sn()

                if discovered_ip_sn_addresses:
                    if self.sn in discovered_ip_sn_addresses:
                        self.ip = discovered_ip_sn_addresses[self.sn]
                    else:
                        raise ValueError(
                            "The provided serial number wasn't found on the network. Provide an IP address instead."
                        )
                else:
                    raise ValueError(
                        "No devices found on the network. Provide an IP address instead."
                    )

            await self.init_webrtc(ip=self.ip)
        elif self.connectionMethod == WebRTCConnectionMethod.LocalAP:
            self.ip = "192.168.12.1"
            await self.init_webrtc(ip=self.ip)

    async def disconnect(self):
        if self.pc:
            await self.pc.close()
            self.pc = None
        self.isConnected = False
        logger.info("WebRTC connection 🔴 disconnected")

    async def reconnect(self):
        await self.disconnect()
        await self.connect()
        logger.info("WebRTC connection 🟢 reconnected")

    def create_webrtc_configuration(
        self,
        turn_server_info: dict[str, Any] | None,
        stun_enable: bool = True,
        turn_enable: bool = True,
    ) -> RTCConfiguration:
        ice_servers: list[RTCIceServer] = []

        if turn_server_info:
            username = turn_server_info.get("user")
            credential = turn_server_info.get("passwd")
            turn_url = turn_server_info.get("realm")

            if username and credential and turn_url:
                if turn_enable:
                    ice_servers.append(
                        RTCIceServer(urls=[turn_url], username=username, credential=credential)
                    )
                if stun_enable:
                    # Use Google's public STUN server
                    stun_url = "stun:stun.l.google.com:19302"
                    ice_servers.append(RTCIceServer(urls=[stun_url]))
            else:
                raise ValueError("Invalid TURN server information")

        configuration = RTCConfiguration(iceServers=ice_servers)

        return configuration

    async def init_webrtc(
        self, turn_server_info: dict[str, Any] | None = None, ip: str | None = None
    ):
        _ = ip

        configuration = self.create_webrtc_configuration(turn_server_info)
        pc = RTCPeerConnection(configuration)
        self.pc = pc

        self.datachannel = WebRTCDataChannel(conn=self, pc=self.pc)

        self.audio = WebRTCAudioChannel(self.pc, self.datachannel)
        self.video = WebRTCVideoChannel(self.pc, self.datachannel)

        @self.pc.on("icegatheringstatechange")
        async def on_ice_gathering_state_change():  # type: ignore
            state = pc.iceGatheringState
            if state == "new":
                logger.info("ICE Gathering State: 🔵 new")
            elif state == "gathering":
                logger.info("ICE Gathering State: 🟡 gathering")
            elif state == "complete":
                logger.info("ICE Gathering State: 🟢 complete")

        @self.pc.on("iceconnectionstatechange")
        async def on_ice_connection_state_change():  # type: ignore
            state = pc.iceConnectionState
            if state == "checking":
                logger.info("ICE Connection State: 🔵 checking")
            elif state == "completed":
                logger.info("ICE Connection State: 🟢 completed")
            elif state == "failed":
                logger.info("ICE Connection State: 🔴 failed")
            elif state == "closed":
                logger.info("ICE Connection State: ⚫ closed")

        @self.pc.on("connectionstatechange")
        async def on_connection_state_change():  # type: ignore
            state = pc.connectionState
            if state == "connecting":
                logger.info("Peer Connection State: 🔵 connecting")
            elif state == "connected":
                self.isConnected = True
                logger.info("Peer Connection State: 🟢 connected")
            elif state == "closed":
                self.isConnected = False
                logger.info("Peer Connection State: ⚫ closed")
            elif state == "failed":
                logger.info("Peer Connection State: 🔴 failed")

        @self.pc.on("signalingstatechange")
        async def on_signaling_state_change():  # type: ignore
            state = pc.signalingState
            if state == "stable":
                logger.info("Signaling State: 🟢 stable")
            elif state == "have-local-offer":
                logger.info("Signaling State: 🟡 have-local-offer")
            elif state == "have-remote-offer":
                logger.info("Signaling State: 🟡 have-remote-offer")
            elif state == "closed":
                logger.info("Signaling State: ⚫ closed")

        @self.pc.on("track")
        async def on_track(track: MediaStreamTrack):  # type: ignore
            logger.info("Track recieved: %s", track.kind)

            if track.kind == "video":
                # await for the first frame, #ToDo make the code more nicer
                frame = await track.recv()
                await self.video.track_handler(track)

            if track.kind == "audio":
                frame = await track.recv()
                while True:
                    frame = await track.recv()
                    await self.audio.frame_handler(frame)

        logger.info("Creating offer...")
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)

        if self.connectionMethod == WebRTCConnectionMethod.Remote and turn_server_info is not None:
            peer_answer_json = await self.get_answer_from_remote_peer(self.pc, turn_server_info)
        elif (
            self.connectionMethod == WebRTCConnectionMethod.LocalSTA
            or self.connectionMethod == WebRTCConnectionMethod.LocalAP
        ):
            if self.ip is None:
                raise ValueError("IP address is required for local connection")
            peer_answer_json = await self.get_answer_from_local_peer(self.pc, self.ip)
        else:
            raise ValueError(f"Invalid connection method: {self.connectionMethod}")

        if peer_answer_json is not None:
            peer_answer = json.loads(peer_answer_json)
        else:
            raise RuntimeError("Could not get SDP from the peer. Check if the Go2 is switched on")

        if peer_answer["sdp"] == "reject":
            raise RuntimeError(
                "Go2 is connected by another WebRTC client. Close your mobile APP and try again."
            )

        await asyncio.sleep(5)

        remote_sdp = RTCSessionDescription(sdp=peer_answer["sdp"], type=peer_answer["type"])
        await self.pc.setRemoteDescription(remote_sdp)

        await self.datachannel.wait_datachannel_open()

    async def get_answer_from_remote_peer(
        self, pc: RTCPeerConnection, turn_server_info: dict[str, Any]
    ):
        sdp_offer = pc.localDescription

        sdp_offer_json = {
            "id": "",
            "turnserver": turn_server_info,
            "sdp": sdp_offer.sdp,
            "type": sdp_offer.type,
            "token": self.token,
        }

        logger.debug("Local SDP created: %s", sdp_offer_json)

        peer_answer_json = send_sdp_to_remote_peer(
            serial=self.sn,
            sdp=json.dumps(sdp_offer_json),
            access_token=self.token,
            public_key=self.public_key,
        )

        return peer_answer_json

    async def get_answer_from_local_peer(self, pc: RTCPeerConnection, ip: str):
        sdp_offer = pc.localDescription

        sdp_offer_json = {
            "id": "STA_localNetwork"
            if self.connectionMethod == WebRTCConnectionMethod.LocalSTA
            else "",
            "sdp": sdp_offer.sdp,
            "type": sdp_offer.type,
            "token": self.token,
        }

        peer_answer_json = send_sdp_to_local_peer(ip, json.dumps(sdp_offer_json))

        return peer_answer_json
