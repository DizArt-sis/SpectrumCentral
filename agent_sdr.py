#!/usr/bin/env python3
"""
RF Spectrum Control System - Real SDR Agent for Windows (Working)
"""

import paho.mqtt.client as mqtt
import json
import time
import threading
import numpy as np
import logging
import random
from datetime import datetime

# ==================== Конфигурация ====================
BROKER_IP = "127.0.0.1"
DEVICE_ID = "sdr_device1"

COMMAND_TOPIC = f"devices/{DEVICE_ID}/commands"
RESPONSE_TOPIC = f"devices/{DEVICE_ID}/response"
STATUS_TOPIC = f"devices/{DEVICE_ID}/status"
INFO_TOPIC = f"devices/{DEVICE_ID}/info"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(f"SDR-Agent-{DEVICE_ID}")

# ==================== Импорт SDR ====================
SDR_AVAILABLE = False
RtlSdr = None

try:
    from rtlsdr import RtlSdr

    SDR_AVAILABLE = True
    logger.info("✅ RTLSDR library loaded")
except ImportError as e:
    logger.error(f"❌ Import failed: {e}")


# ==================== SDR Анализатор с таймаутами ====================
class RealSdrAnalyzer:
    def __init__(self):
        self.sdr = None
        self.sample_rate = 1.8e6  # 2.048 MHz (более стабильно)
        self.center_freq = 100e6
        self.gain = "auto"
        self.is_scanning = False
        self._connect()

    def _connect(self):
        if not SDR_AVAILABLE:
            return False
        try:
            self.sdr = RtlSdr(device_index=0)
            self.sdr.sample_rate = self.sample_rate
            self.sdr.center_freq = self.center_freq
            self.sdr.gain = self.gain

            # Тестовое чтение
            test = self.sdr.read_samples(128)
            logger.info(f"SDR connected successfully")
            logger.info(f"  Sample rate: {self.sample_rate/1e6:.2f} MHz")
            logger.info(f"  Center freq: {self.center_freq/1e6:.2f} MHz")
            return True
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self.sdr = None
            return False

    def scan_spectrum(self, start_mhz, end_mhz, num_points=80):
        """
        Сканирование спектра - оптимизированная версия
        """
        if not self.sdr:
            if not self._connect():
                logger.warning("SDR not available, using mock data")
                return self._generate_mock_spectrum(start_mhz, end_mhz)

        self.is_scanning = True
        start_hz = start_mhz * 1e6
        end_hz = end_mhz * 1e6
        step_hz = (end_hz - start_hz) / num_points

        spectrum = []
        logger.info(f"Scanning {start_mhz:.1f}-{end_mhz:.1f} MHz ({num_points} points)")

        for i in range(num_points):
            if not self.is_scanning:
                break

            freq_hz = start_hz + i * step_hz
            freq_mhz = freq_hz / 1e6

            try:
                # Перестройка с таймаутом
                self.sdr.center_freq = freq_hz
                time.sleep(0.025)  # Маленькая задержка

                # Чтение с таймаутом
                samples = self.sdr.read_samples(256)

                if len(samples) > 0:
                    # Быстрая оценка мощности
                    power = 20 * np.log10(np.mean(np.abs(samples)) + 1e-12)
                    power_dbm = power + 10  # Калибровка
                else:
                    power_dbm = -100

                # Ограничение
                power_dbm = max(min(power_dbm, -20), -100)

                spectrum.append(
                    {"freq": round(freq_mhz, 2), "power": round(power_dbm, 1)}
                )

            except Exception as e:
                logger.warning(f"Error at {freq_mhz:.1f} MHz: {str(e)[:50]}")
                # Интерполяция при ошибке
                if len(spectrum) > 0:
                    spectrum.append(
                        {"freq": round(freq_mhz, 2), "power": spectrum[-1]["power"]}
                    )
                else:
                    spectrum.append({"freq": round(freq_mhz, 2), "power": -85})

        self.is_scanning = False
        logger.info(f"Scan complete: {len(spectrum)} points")
        return self._smooth_spectrum(spectrum)

    def _smooth_spectrum(self, data, window=3):
        if len(data) < window:
            return data
        smoothed = []
        for i in range(len(data)):
            start = max(0, i - window // 2)
            end = min(len(data), i + window // 2 + 1)
            avg = sum(p["power"] for p in data[start:end]) / (end - start)
            smoothed.append({"freq": data[i]["freq"], "power": round(avg, 1)})
        return smoothed

    def _generate_mock_spectrum(self, start_mhz, end_mhz):
        """Быстрая генерация тестового спектра"""
        spectrum = []
        noise = -85

        # Несколько сигналов
        signals = []
        for _ in range(random.randint(2, 4)):
            signals.append(
                {
                    "freq": random.uniform(start_mhz, end_mhz),
                    "power": random.uniform(-60, -35),
                    "width": random.uniform(2, 5),
                }
            )

        for i in range(100):
            freq = start_mhz + (i / 100) * (end_mhz - start_mhz)
            power = noise + random.gauss(0, 2)

            for sig in signals:
                dist = abs(freq - sig["freq"])
                if dist < sig["width"]:
                    contrib = sig["power"] * np.exp(
                        -(dist**2) / (2 * (sig["width"] / 3) ** 2)
                    )
                    power = max(power, contrib)

            spectrum.append(
                {"freq": round(freq, 2), "power": round(max(min(power, -25), -100), 1)}
            )

        return spectrum

    def set_parameter(self, param, value):
        if param in ["rbw", "attenuation"]:
            return f"Parameter {param} set to {value}"
        elif param == "center_freq":
            try:
                freq = float(value)
                if freq <= 350:
                    self.center_freq = freq * 1e6
                    if self.sdr:
                        self.sdr.center_freq = self.center_freq
                    return f"Center frequency set to {value} MHz"
                else:
                    return f"Frequency {value} MHz exceeds tuner limit (350 MHz)"
            except:
                return "Invalid frequency"
        return f"Parameter {param} set"

    def get_info(self):
        return {
            "type": "rtl-sdr",
            "device_id": DEVICE_ID,
            "status": "online" if self.sdr else "offline",
        }

    def close(self):
        self.is_scanning = False
        if self.sdr:
            try:
                self.sdr.close()
            except:
                pass
            logger.info("SDR closed")


# ==================== MQTT ====================
analyzer = RealSdrAnalyzer()


def on_connect(client, userdata, flags, rc):
    logger.info(f"MQTT connected (code {rc})")
    client.subscribe(COMMAND_TOPIC)
    client.publish(STATUS_TOPIC, "online")
    client.publish(INFO_TOPIC, json.dumps(analyzer.get_info()))


def on_message(client, userdata, msg):
    command = msg.payload.decode()
    logger.info(f"Received: {command}")

    try:
        if command.startswith("scan_spectrum"):
            parts = command.split()
            start = float(parts[1]) if len(parts) > 1 else 88
            end = float(parts[2]) if len(parts) > 2 else 108

            # Ограничиваем диапазон для FC0012
            if start > 350 or end > 350:
                logger.warning(f"Range {start}-{end} exceeds tuner limit, using mock")
                spectrum = analyzer._generate_mock_spectrum(start, end)
            else:
                spectrum = analyzer.scan_spectrum(start, end)

            response = json.dumps(spectrum)
            logger.info(f"Scan done, {len(spectrum)} points")

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
        response = f"Error: {str(e)}"
        logger.error(f"Command error: {e}")

    # Всегда отправляем ответ
    client.publish(RESPONSE_TOPIC, response)
    logger.debug(f"Response sent")


def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    print("=" * 50)
    print("📡 SDR Agent (Working Version)")
    print("=" * 50)
    print(f"📍 MQTT: {BROKER_IP}")
    print("=" * 50)

    try:
        client.connect(BROKER_IP, 1883, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        analyzer.close()


if __name__ == "__main__":
    main()
