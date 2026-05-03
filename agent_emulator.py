#!/usr/bin/env python3
"""
RF Spectrum Control System - Emulator Agent
Для тестирования без реального SDR
"""

import paho.mqtt.client as mqtt
import json
import time
import threading
import random
import math
import logging
from datetime import datetime

# -----------------Конфигурация ------------------------
BROKER_IP = "localhost"  # Изменяем на IP нашего брокера/сервера
DEVICE_ID = "emulator_device1"  # Изменяем на название нашего устройства

COMMAND_TOPIC = f"devices/{DEVICE_ID}/commands"
RESPONSE_TOPIC = f"devices/{DEVICE_ID}/response"
STATUS_TOPIC = f"devices/{DEVICE_ID}/status"
INFO_TOPIC = f"devices/{DEVICE_ID}/info"

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(f"Emulator-{DEVICE_ID}")


# ---------------------- Параметры -------------------
class EmulatorAnalyzer:
    def __init__(self):
        self.rbw = 100  # kHz
        self.attenuation = 10  # dB
        self.center_freq = 500  # MHz

    def generate_spectrum(self, start_mhz, end_mhz, num_points=300):
        """Генерация реалистичного спектра"""
        spectrum = []

        # Базовый шум
        noise_floor = -85

        # Генерируем несколько сигналов
        num_signals = random.randint(2, 5)
        signals = []
        for _ in range(num_signals):
            freq = random.uniform(start_mhz, end_mhz)
            power = random.uniform(-55, -30)
            width = random.uniform(2, 8)
            signals.append({"freq": freq, "power": power, "width": width})

        for i in range(num_points):
            freq = start_mhz + (i / num_points) * (end_mhz - start_mhz)

            # Шум
            power = noise_floor + random.gauss(0, 3)

            # Добавляем сигналы
            for sig in signals:
                distance = abs(freq - sig["freq"])
                if distance < sig["width"]:
                    # Гауссовский пик
                    contribution = sig["power"] * math.exp(
                        -(distance**2) / (2 * (sig["width"] / 2) ** 2)
                    )
                    power = max(power, contribution)

            # Иногда добавляем импульсную помеху
            if random.random() < 0.02:
                power += random.uniform(10, 20)

            spectrum.append(
                {"freq": round(freq, 2), "power": round(max(min(power, -20), -100), 1)}
            )

        return spectrum

    def set_parameter(self, param, value):
        if param == "rbw":
            self.rbw = float(value)
            return f"RBW set to {value} kHz"
        elif param == "attenuation":
            self.attenuation = int(value)
            return f"Attenuation set to {value} dB"
        elif param == "center_freq":
            self.center_freq = float(value)
            return f"Center frequency set to {value} MHz"
        else:
            return f"Parameter {param} set to {value}"

    def get_info(self):
        return {
            "type": "emulator",
            "device_id": DEVICE_ID,
            "rbw_khz": self.rbw,
            "attenuation_db": self.attenuation,
            "center_freq_mhz": self.center_freq,
        }


# ------------------- MQTT -------------------------
analyzer = EmulatorAnalyzer()


def on_connect(client, userdata, flags, rc):
    logger.info(f"Connected to MQTT broker with code {rc}")
    client.subscribe(COMMAND_TOPIC)
    client.publish(STATUS_TOPIC, "online")

    info = analyzer.get_info()
    client.publish(INFO_TOPIC, json.dumps(info))

    def heartbeat():
        while True:
            time.sleep(30)
            client.publish(STATUS_TOPIC, "online")

    threading.Thread(target=heartbeat, daemon=True).start()


def on_message(client, userdata, msg):
    command = msg.payload.decode()
    logger.info(f"Command: {command}")

    try:
        if command.startswith("scan_spectrum"):
            parts = command.split()
            if len(parts) >= 3:
                start = float(parts[1])
                end = float(parts[2])
            else:
                start, end = 400, 600

            spectrum = analyzer.generate_spectrum(start, end)
            response = json.dumps(spectrum)

        elif command.startswith("set_"):
            parts = command.split()
            param = command.split("_")[1].split()[0]
            value = parts[1] if len(parts) > 1 else "0"
            response = analyzer.set_parameter(param, value)

        elif command == "get_info":
            response = json.dumps(analyzer.get_info())
        elif command == "ping":
            response = "pong"
        else:
            response = f"Unknown: {command}"

    except Exception as e:
        response = f"Error: {e}"

    client.publish(RESPONSE_TOPIC, response)


def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    print("=" * 60)
    print(f"🎮 Emulator Agent: {DEVICE_ID}")
    print("=" * 60)

    client.connect(BROKER_IP, 1883, 60)
    client.loop_forever()


if __name__ == "__main__":
    main()
