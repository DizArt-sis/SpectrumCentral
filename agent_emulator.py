#!/usr/bin/env python3
"""
RF Spectrum Control System - Emulator Agent
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
BROKER_IP = "localhost"
DEVICE_ID = "emulator_device1"

COMMAND_TOPIC = f"devices/{DEVICE_ID}/commands"
RESPONSE_TOPIC = f"devices/{DEVICE_ID}/response"
STATUS_TOPIC = f"devices/{DEVICE_ID}/status"
INFO_TOPIC = f"devices/{DEVICE_ID}/info"
# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------------------- Параметры -------------------
class EmulatorAnalyzer:
    def __init__(self):
        self.rbw = 100
        self.attenuation = 10
        
    def generate_spectrum(self, start_mhz, end_mhz, num_points=200):
        """Генерация РЕАЛИСТИЧНОГО спектра"""
        spectrum = []
        
        # ✅ УРОВЕНЬ ШУМА: -95 до -85 dBm (реалистично)
        noise_floor = random.uniform(-95, -85)
        
        # ✅ ВСЕГО 2-4 СИГНАЛА во всем диапазоне
        num_signals = random.randint(2, 4)
        signals = []
        
        for _ in range(num_signals):
            freq = random.uniform(start_mhz + 1, end_mhz - 1)
            # Мощность сигналов: -65 до -35 dBm (реалистично)
            power = random.uniform(-65, -35)
            width = random.uniform(1.0, 3.0)
            signals.append({"freq": freq, "power": power, "width": width})
        
        logger.info(f"Генерация спектра: {start_mhz}-{end_mhz} MHz, {num_signals} сигналов")
        
        for i in range(num_points):
            freq = start_mhz + (i / num_points) * (end_mhz - start_mhz)
            
            # Базовый шум
            power = noise_floor + random.gauss(0, 1.5)
            
            # Добавляем сигналы
            for sig in signals:
                distance = abs(freq - sig["freq"])
                if distance < sig["width"]:
                    contribution = sig["power"] * math.exp(-(distance**2) / (2 * (sig["width"]/3)**2))
                    power = max(power, contribution)
            
            # Редкие импульсы (1% точек)
            if random.random() < 0.01:
                power += random.uniform(8, 15)
            
            spectrum.append({
                "freq": round(freq, 2),
                "power": round(max(min(power, -25), -100), 1)
            })
        
        return spectrum
    
    def set_parameter(self, param, value):
        if param == "rbw":
            self.rbw = float(value)
            return f"RBW set to {value} kHz"
        elif param == "attenuation":
            self.attenuation = int(value)
            return f"Attenuation set to {value} dB"
        else:
            return f"Parameter set: {param}={value}"
    
    def get_info(self):
        return {"type": "emulator", "device_id": DEVICE_ID, "rbw_khz": self.rbw}

# ------------------- MQTT -------------------------
analyzer = EmulatorAnalyzer()

def on_connect(client, userdata, flags, rc):
    logger.info(f"MQTT connected (code {rc})")
    client.subscribe(COMMAND_TOPIC)
    client.publish(STATUS_TOPIC, "online")
    client.publish(INFO_TOPIC, json.dumps(analyzer.get_info()))

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
                start, end = 88, 108
            
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
        logger.error(f"Error: {e}")
    
    client.publish(RESPONSE_TOPIC, response)

def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    
    print("=" * 50)
    print("🎮 Emulator Agent ")
    print("=" * 50)
    
    client.connect(BROKER_IP, 1883, 60)
    client.loop_forever()

if __name__ == "__main__":
    main()
