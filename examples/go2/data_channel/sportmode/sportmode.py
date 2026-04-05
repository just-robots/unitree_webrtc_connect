import asyncio
import logging
import json
import sys
from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection, WebRTCConnectionMethod
from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

async def main():
    conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalAP)
    try:
        # Connect to the WebRTC service.
        await conn.connect()

        ####### NORMAL MODE ########
        logger.info("Checking current motion mode...")

        # Get the current motion_switcher status
        response = await conn.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["MOTION_SWITCHER"], 
            {"api_id": 1001}
        )

        if response['data']['header']['status']['code'] == 0:
            data = json.loads(response['data']['data'])
            current_motion_switcher_mode = data['name']
            logger.info(f"Current motion mode: {current_motion_switcher_mode}")


        response = await conn.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["OBSTACLES_AVOID"], 
            {
                "api_id": 1001,
                "parameter": {"enable": False}
            }
        )

        logger.info(f"Obstacles avoidance: {response}")

        # Perform a "Hello" movement
        logger.info("Performing 'Hello' movement...")
        await conn.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["SPORT_MOD"], 
            {"api_id": SPORT_CMD["Hello"]}
        )

        # await asyncio.sleep(1)

        # # Perform a "Move Forward" movement
        # print("Moving forward...")
        # await conn.datachannel.pub_sub.publish_request_new(
        #     RTC_TOPIC["SPORT_MOD"], 
        #     {
        #         "api_id": SPORT_CMD["Move"],
        #         "parameter": {"x": 0.5, "y": 0, "z": 0}
        #     }
        # )

        # await asyncio.sleep(3)

        # # Perform a "Move Backward" movement
        # print("Moving backward...")
        # await conn.datachannel.pub_sub.publish_request_new(
        #     RTC_TOPIC["SPORT_MOD"], 
        #     {
        #         "api_id": SPORT_CMD["Move"],
        #         "parameter": {"x": +0.5, "y": 0, "z": 0}
        #     }
        # )

        # await asyncio.sleep(3)

        # ####### AI MODE ########

        # # Switch to AI mode
        # print("Switching motion mode to 'AI'...")
        # await conn.datachannel.pub_sub.publish_request_new(
        #     RTC_TOPIC["MOTION_SWITCHER"], 
        #     {
        #         "api_id": 1002,
        #         "parameter": {"name": "ai"}
        #     }
        # )
        # await asyncio.sleep(10)

        # # Switch to Handstand Mode
        # print("Switching to Handstand Mode...")
        # await conn.datachannel.pub_sub.publish_request_new(
        #     RTC_TOPIC["SPORT_MOD"], 
        #     {
        #         "api_id": SPORT_CMD["StandOut"],
        #         "parameter": {"data": True}
        #     }
        # )

        # await asyncio.sleep(5)

        # # Switch back to StandUp Mode
        # print("Switching back to StandUp Mode...")
        # await conn.datachannel.pub_sub.publish_request_new(
        #     RTC_TOPIC["SPORT_MOD"], 
        #     {
        #         "api_id": SPORT_CMD["StandOut"],
        #         "parameter": {"data": False}
        #     }
        # )

        # await asyncio.sleep(5)
        # Perform a backflip
        # print(f"Performing BackFlip")
        # await conn.datachannel.pub_sub.publish_request_new(
        #     RTC_TOPIC["SPORT_MOD"], 
        #     {
        #         "api_id": SPORT_CMD["Move"],
        #         "parameter": {"x": 0.5, "y": 0, "z": 0}
        #     }
        # )

        # await asyncio.sleep(3)

        # # Perform a "Move Backward" movement
        # print("Moving backward...")
        # await conn.datachannel.pub_sub.publish_request_new(
        #     RTC_TOPIC["SPORT_MOD"], 
        #     {
        #         "api_id": SPORT_CMD["Move"],
        #         "parameter": {"x": +0.5, "y": 0, "z": 0}
        #     }
        # )

        # await asyncio.sleep(3)

        # Keep the program running for a while
        await asyncio.sleep(3600)
    
    except ValueError as e:
        # Log any value errors that occur during the process.
        logging.error(f"An error occurred: {e}")
    finally:
        await conn.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Handle Ctrl+C to exit gracefully.
        print("\nProgram interrupted by user")
        sys.exit(0)