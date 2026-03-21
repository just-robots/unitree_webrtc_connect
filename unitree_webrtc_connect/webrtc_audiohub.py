import json
import base64
import time
import uuid
import os
import hashlib
from pydub import AudioSegment  # type: ignore[reportMissingTypeStubs]
from unitree_webrtc_connect.constants import AUDIO_API
from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection
import asyncio
import logging

CHUNK_SIZE = 61440


logger = logging.getLogger(__name__)


class WebRTCAudioHub:
    def __init__(self, connection: UnitreeWebRTCConnection):
        self.conn = connection
        self.data_channel = None
        self._setup_data_channel()

    def _setup_data_channel(self):
        """Setup the WebRTC data channel for audio control"""
        if not self.conn.datachannel:
            logger.error("WebRTC connection not established")
            raise RuntimeError("WebRTC connection not established")
        self.data_channel = self.conn.datachannel

    async def get_audio_list(self):
        """Get list of available audio files"""
        if self.data_channel is None:
            raise ValueError("datachannel isn't configured")
        response = await self.data_channel.pub_sub.publish_request_new(
            "rt/api/audiohub/request",
            {"api_id": AUDIO_API["GET_AUDIO_LIST"], "parameter": json.dumps({})},
        )
        return response

    async def play_by_uuid(self, uuid: str):
        """Play audio by UUID"""
        if self.data_channel is None:
            raise ValueError("datachannel isn't configured")
        await self.data_channel.pub_sub.publish_request_new(
            "rt/api/audiohub/request",
            {
                "api_id": AUDIO_API["SELECT_START_PLAY"],
                "parameter": json.dumps({"unique_id": uuid}),
            },
        )

    async def pause(self):
        """Pause current audio playback"""
        if self.data_channel is None:
            raise ValueError("datachannel isn't configured")
        await self.data_channel.pub_sub.publish_request_new(
            "rt/api/audiohub/request", {"api_id": AUDIO_API["PAUSE"], "parameter": json.dumps({})}
        )

    async def resume(self):
        """Resume paused audio playback"""
        if self.data_channel is None:
            raise ValueError("datachannel isn't configured")
        await self.data_channel.pub_sub.publish_request_new(
            "rt/api/audiohub/request",
            {"api_id": AUDIO_API["UNSUSPEND"], "parameter": json.dumps({})},
        )

    async def set_play_mode(self, play_mode: str):
        """Set audio play mode (single_cycle, no_cycle, list_loop)"""
        if self.data_channel is None:
            raise ValueError("datachannel isn't configured")
        await self.data_channel.pub_sub.publish_request_new(
            "rt/api/audiohub/request",
            {
                "api_id": AUDIO_API["SET_PLAY_MODE"],
                "parameter": json.dumps({"play_mode": play_mode}),
            },
        )

    async def rename_record(self, uuid: str, new_name: str):
        """Rename an audio record"""
        if self.data_channel is None:
            raise ValueError("datachannel isn't configured")
        await self.data_channel.pub_sub.publish_request_new(
            "rt/api/audiohub/request",
            {
                "api_id": AUDIO_API["SELECT_RENAME"],
                "parameter": json.dumps({"unique_id": uuid, "new_name": new_name}),
            },
        )

    async def delete_record(self, uuid: str):
        """Delete an audio record"""
        if self.data_channel is None:
            raise ValueError("datachannel isn't configured")
        await self.data_channel.pub_sub.publish_request_new(
            "rt/api/audiohub/request",
            {"api_id": AUDIO_API["SELECT_DELETE"], "parameter": json.dumps({"unique_id": uuid})},
        )

    async def get_play_mode(self):
        """Get current play mode"""
        if self.data_channel is None:
            raise ValueError("datachannel isn't configured")
        response = await self.data_channel.pub_sub.publish_request_new(
            "rt/api/audiohub/request",
            {"api_id": AUDIO_API["GET_PLAY_MODE"], "parameter": json.dumps({})},
        )
        return response

    async def upload_audio_file(self, audiofile_path: str):
        """Upload audio file (MP3 or WAV)"""
        if self.data_channel is None:
            raise ValueError("datachannel isn't configured")

        # Convert MP3 to WAV if necessary
        if audiofile_path.endswith(".mp3"):
            logger.info("Converting MP3 to WAV")
            audio = AudioSegment.from_mp3(audiofile_path)
            # Set specific audio parameters for compatibility
            audio = audio.set_frame_rate(44100)  # Standard sample rate
            wav_file_path = audiofile_path.replace(".mp3", ".wav")
            audio.export(wav_file_path, format="wav", parameters=["-ar", "44100"])
        else:
            wav_file_path = audiofile_path

        # Read the WAV file
        with open(wav_file_path, "rb") as f:  # noqa: ASYNC230
            audio_data = f.read()

        # Generate a unique ID for the audio file
        _unique_id = str(uuid.uuid4())

        try:
            # Calculate MD5 of the file
            file_md5 = hashlib.md5(audio_data).hexdigest()  # noqa: S324

            # Convert to base64
            b64_data = base64.b64encode(audio_data).decode("utf-8")

            # Split into smaller chunks (4KB each)
            chunk_size = 4096
            chunks = [b64_data[i : i + chunk_size] for i in range(0, len(b64_data), chunk_size)]
            total_chunks = len(chunks)

            logger.info(f"Splitting file into {total_chunks} chunks")

            response = None
            # Send each chunk
            for i, chunk in enumerate(chunks, 1):
                parameter = {
                    "file_name": os.path.splitext(os.path.basename(audiofile_path))[0],
                    "file_type": "wav",
                    "file_size": len(audio_data),
                    "current_block_index": i,
                    "total_block_number": total_chunks,
                    "block_content": chunk,
                    "current_block_size": len(chunk),
                    "file_md5": file_md5,
                    "create_time": int(time.time() * 1000),
                }
                logger.info(json.dumps(parameter, ensure_ascii=True))
                # Send the chunk
                logger.info(f"Sending chunk {i}/{total_chunks}")

                response = await self.data_channel.pub_sub.publish_request_new(
                    "rt/api/audiohub/request",
                    {
                        "api_id": AUDIO_API["UPLOAD_AUDIO_FILE"],
                        "parameter": json.dumps(parameter, ensure_ascii=True),
                    },
                )

                # Wait a small amount between chunks
                await asyncio.sleep(0.1)

            logger.info("All chunks sent")
            return response

        except Exception:
            logger.exception("Error uploading audio file")
            raise

    async def enter_megaphone(self):
        """Enter megaphone mode"""
        if self.data_channel is None:
            raise ValueError("datachannel isn't configured")
        await self.data_channel.pub_sub.publish_request_new(
            "rt/api/audiohub/request",
            {"api_id": AUDIO_API["ENTER_MEGAPHONE"], "parameter": json.dumps({})},
        )

    async def exit_megaphone(self):
        """Exit megaphone mode"""
        if self.data_channel is None:
            raise ValueError("datachannel isn't configured")
        await self.data_channel.pub_sub.publish_request_new(
            "rt/api/audiohub/request",
            {"api_id": AUDIO_API["EXIT_MEGAPHONE"], "parameter": json.dumps({})},
        )

    async def upload_megaphone(self, audiofile_path: str):
        """Upload audio file (MP3 or WAV)"""
        if self.data_channel is None:
            raise ValueError("datachannel isn't configured")

        # Convert MP3 to WAV if necessary
        if audiofile_path.endswith(".mp3"):
            logger.info("Converting MP3 to WAV")
            audio: AudioSegment = AudioSegment.from_mp3(audiofile_path)
            # Set specific audio parameters for compatibility
            audio = audio.set_frame_rate(44100)  # Standard sample rate
            wav_file_path = audiofile_path.replace(".mp3", ".wav")
            audio.export(wav_file_path, format="wav", parameters=["-ar", "44100"])
        else:
            wav_file_path = audiofile_path

        # Read and chunk the WAV file
        with open(wav_file_path, "rb") as f:  # noqa: ASYNC230
            audio_data = f.read()

        try:
            # Calculate MD5 of the file
            _file_md5 = hashlib.md5(audio_data).hexdigest()  # noqa: S324

            # Convert to base64
            b64_data = base64.b64encode(audio_data).decode("utf-8")

            # Split into smaller chunks (4KB each)
            chunk_size = 4096
            chunks = [b64_data[i : i + chunk_size] for i in range(0, len(b64_data), chunk_size)]
            total_chunks = len(chunks)

            logger.info(f"Splitting file into {total_chunks} chunks")

            response = None
            # Send each chunk
            for i, chunk in enumerate(chunks, 1):
                parameter = {
                    "current_block_size": len(chunk),
                    "block_content": chunk,
                    "current_block_index": i,
                    "total_block_number": total_chunks,
                }
                logger.info(json.dumps(parameter, ensure_ascii=True))
                # Send the chunk
                logger.info(f"Sending chunk {i}/{total_chunks}")

                response = await self.data_channel.pub_sub.publish_request_new(
                    "rt/api/audiohub/request",
                    {
                        "api_id": AUDIO_API["UPLOAD_MEGAPHONE"],
                        "parameter": json.dumps(parameter, ensure_ascii=True),
                    },
                )

                # Wait a small amount between chunks
                await asyncio.sleep(0.1)

            logger.info("All chunks sent")
            return response
        except Exception:
            logger.exception("Error uploading audio file")
            raise
