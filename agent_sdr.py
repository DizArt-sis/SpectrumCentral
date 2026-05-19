#!/usr/bin/env python3

import paho.mqtt.client as mqtt
import subprocess
import tempfile
import csv
import json
import time
import socket
import logging
import os

# ================= CONFIG =================

BROKER_IP = "127.0.0.1"

BROKER_PORT = 1883

DEVICE_ID = socket.gethostname()

RTL_POWER_PATH = r"C:\rtl-sdr\rtl_power.exe"

COMMAND_TOPIC = f"devices/{DEVICE_ID}/commands"

RESPONSE_TOPIC = f"devices/{DEVICE_ID}/response"

STATUS_TOPIC = f"devices/{DEVICE_ID}/status"

# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("RTL_AGENT")

# ==========================================


class RTLPowerScanner:

    def __init__(self):

        if not os.path.exists(RTL_POWER_PATH):

            raise Exception(
                f"rtl_power not found: {RTL_POWER_PATH}"
            )

        logger.info("rtl_power detected")

    def scan_spectrum(
        self,
        start_mhz,
        end_mhz,
        bin_size_khz=100
    ):

        logger.info(
            f"Scanning {start_mhz}-{end_mhz} MHz"
        )

        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".csv"
        )

        temp_path = temp_file.name

        temp_file.close()

        command = [

            RTL_POWER_PATH,

            "-f",

            f"{start_mhz}M:{end_mhz}M:{bin_size_khz}k",

            "-1",

            temp_path
        ]

        logger.info("Executing rtl_power")

        result = subprocess.run(
            command,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:

            raise Exception(
                f"rtl_power failed:\n{result.stderr}"
            )

        logger.info("rtl_power completed")

        points = self.parse_csv(temp_path)

        os.remove(temp_path)

        logger.info(
            f"Parsed {len(points)} spectrum points"
        )

        return points

    def parse_csv(self, filename):

        points = []

        with open(filename, newline="") as csvfile:

            reader = csv.reader(csvfile)

            for row in reader:

                try:

                    if len(row) < 7:
                        continue

                    start_freq = float(row[2])

                    stop_freq = float(row[3])

                    step = float(row[4])

                    powers = row[6:]

                    for i, power in enumerate(powers):

                        try:

                            freq = start_freq + i * step

                            points.append({

                                "freq": round(
                                    freq / 1e6,
                                    3
                                ),

                                "power": float(power)
                            })

                        except:
                            continue

                except Exception as e:

                    logger.warning(
                        f"CSV parse error: {e}"
                    )

        return points


scanner = RTLPowerScanner()

# ==========================================


def on_connect(client, userdata, flags, rc):

    logger.info(
        f"MQTT connected: {rc}"
    )

    client.subscribe(COMMAND_TOPIC)

    client.publish(
        STATUS_TOPIC,
        "online"
    )


def handle_scan(client, payload):

    start_freq = payload.get(
        "start_freq",
        88
    )

    end_freq = payload.get(
        "end_freq",
        108
    )

    points = scanner.scan_spectrum(
        start_freq,
        end_freq
    )

    response = {

        "device_id": DEVICE_ID,

        "start_freq": start_freq,

        "end_freq": end_freq,

        "timestamp": time.time(),

        "points": points
    }

    client.publish(

        RESPONSE_TOPIC,

        json.dumps(response),

        qos=1
    )

    logger.info("Spectrum response sent")


def on_message(client, userdata, msg):

    try:

        payload = json.loads(
            msg.payload.decode()
        )

        logger.info(
            f"COMMAND: {payload}"
        )

        action = payload.get("action")

        if action == "scan":

            handle_scan(
                client,
                payload
            )

        elif action == "ping":

            client.publish(
                RESPONSE_TOPIC,
                "pong"
            )

        else:

            logger.warning(
                f"Unknown action: {action}"
            )

    except Exception as e:

        logger.error(
            f"COMMAND ERROR: {e}"
        )

        client.publish(

            RESPONSE_TOPIC,

            json.dumps({

                "error": str(e)

            })
        )


# ==========================================


def main():

    client = mqtt.Client()

    client.on_connect = on_connect

    client.on_message = on_message

    logger.info("Starting SDR Agent")

    client.connect(
        BROKER_IP,
        BROKER_PORT,
        60
    )

    client.loop_start()

    try:

        while True:

            client.publish(
                STATUS_TOPIC,
                "online"
            )

            time.sleep(10)

    except KeyboardInterrupt:

        logger.info("Stopping agent")

    finally:

        client.loop_stop()


if __name__ == "__main__":

    main()
