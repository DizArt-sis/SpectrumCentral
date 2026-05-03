#!/usr/bin/env python3
"""
RF Spectrum Control System - Real SDR Agent
Поддерживает RTL-SDR (RTL2832U) устройства
"""

import paho.mqtt.client as mqtt
import json
import time
import threading
import numpy as np
import logging
import sys
from datetime import datetime

# -----------------Конфигурация ------------------------
BROKER_IP = "localhost"
DEVICE_ID = "sdr_device1"  # Можно изменить

COMMAND_TOPIC = f"devices/{DEVICE_ID}/commands"
RESPONSE_TOPIC = f"devices/{DEVICE_ID}/response"
STATUS_TOPIC = f"devices/{DEVICE_ID}/status"
INFO_TOPIC = f"devices/{DEVICE_ID}/info"

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(f"SDR-Agent-{DEVICE_ID}")

# ------------------- Попытка импорта SDR библиотеки ------------------------
try:
    from rtlsdr import RtlSdr, LibUSBError
    SDR_AVAILABLE = True
    logger.info("✅ RTLSDR library loaded successfully")
except ImportError as e:
    SDR_AVAILABLE = False
    logger.error(f"❌ RTLSDR library not found: {e}")
    logger.error("   Install: pip install pyrtlsdr[lib]")
    sys.exit(1)

# ---------------------- SDR Анализатор ---------------------------------------
class RealSdrAnalyzer:
    """Реальный анализатор спектра на базе RTL-SDR"""
    
    def __init__(self, device_index=0):
        self.sdr = None
        self.device_index = device_index
        self.sample_rate = 2.4e6  # 2.4 MHz
        self.center_freq = 100e6   # 100 MHz
        self.gain = 'auto'
        self._connect()
        
    def _connect(self):
        """Подключение к SDR устройству"""
        try:
            self.sdr = RtlSdr(self.device_index)
            self.sdr.sample_rate = self.sample_rate
            self.sdr.center_freq = self.center_freq
            self.sdr.gain = self.gain
            logger.info(f"SDR connected (index={self.device_index})")
            logger.info(f"  Sample rate: {self.sample_rate/1e6:.2f} MHz")
            logger.info(f"  Center freq: {self.center_freq/1e6:.2f} MHz")
            return True
        except LibUSBError as e:
            logger.error(f"USB error: {e}")
            self.sdr = None
            return False
        except Exception as e:
            logger.error(f"Failed to connect to SDR: {e}")
            self.sdr = None
            return False
    
    def scan_spectrum(self, start_mhz, end_mhz, num_points=300):
        """
        Сканирование спектра путем перестройки SDR
        start_mhz, end_mhz - в MHz
        """
        if not self.sdr:
            if not self._connect():
                return self._generate_mock_spectrum(start_mhz, end_mhz)
        
        start_hz = start_mhz * 1e6
        end_hz = end_mhz * 1e6
        step_hz = (end_hz - start_hz) / num_points
        
        spectrum = []
        logger.info(f"Scanning {start_mhz:.1f}-{end_mhz:.1f} MHz ({num_points} points)")
        
        for i in range(num_points):
            freq_hz = start_hz + i * step_hz
            freq_mhz = freq_hz / 1e6
            
            try:
                # Перестраиваем частоту
                self.sdr.center_freq = freq_hz
                # Небольшая задержка для стабилизации
                time.sleep(0.008)
                
                # Читаем сэмплы
                samples = self.sdr.read_samples(512)
                
                if len(samples) > 0:
                    # Оценка мощности (RMS)
                    power_rms = np.sqrt(np.mean(np.abs(samples)**2))
                    # Конвертация в dB (относительный уровень)
                    if power_rms > 0:
                        power_db = 20 * np.log10(power_rms + 1e-12)
                        # Калибровка (приблизительная)
                        power_dbm = power_db + 10
                    else:
                        power_dbm = -100
                else:
                    power_dbm = -100
                
                # Ограничиваем диапазон
                power_dbm = max(min(power_dbm, -20), -100)
                
                spectrum.append({
                    "freq": round(freq_mhz, 2),
                    "power": round(power_dbm, 1)
                })
                
                # Прогресс
                if (i + 1) % 50 == 0:
                    logger.debug(f"  Progress: {i+1}/{num_points}")
                    
            except Exception as e:
                logger.error(f"Error at {freq_mhz:.1f} MHz: {e}")
                spectrum.append({
                    "freq": round(freq_mhz, 2),
                    "power": -100
                })
        
        # Интерполяция для сглаживания
        return self._smooth_spectrum(spectrum)
    
    def _smooth_spectrum(self, data, window_size=5):
        """Сглаживание спектра (moving average)"""
        if len(data) < window_size:
            return data
        
        powers = [p["power"] for p in data]
        freqs = [p["freq"] for p in data]
        
        # Простое скользящее среднее
        smoothed = []
        for i in range(len(powers)):
            start = max(0, i - window_size // 2)
            end = min(len(powers), i + window_size // 2 + 1)
            avg_power = sum(powers[start:end]) / (end - start)
            smoothed.append({
                "freq": freqs[i],
                "power": round(avg_power, 1)
            })
        
        return smoothed
    
    def _generate_mock_spectrum(self, start_mhz, end_mhz):
        """Генерация тестового спектра (если SDR недоступен)"""
        logger.warning("SDR not available, generating mock spectrum")
        num_points = 200
        spectrum = []
        
        for i in range(num_points):
            freq = start_mhz + (i / num_points) * (end_mhz - start_mhz)
            # Имитация сигналов
            power = -80 + np.random.normal(0, 5)
            
            # Добавляем искусственные пики
            if 101 < freq < 103:
                power = -35 + np.random.normal(0, 2)
            elif 107.5 < freq < 108:
                power = -40 + np.random.normal(0, 2)
            
            spectrum.append({
                "freq": round(freq, 2),
                "power": round(max(min(power, -20), -100), 1)
            })
        
        return spectrum
    
    def set_parameter(self, param, value):
        """Установка параметра SDR"""
        if not self.sdr:
            return "SDR not connected"
        
        try:
            if param == "center_freq":
                self.center_freq = float(value) * 1e6
                self.sdr.center_freq = self.center_freq
                return f"Center frequency set to {value} MHz"
            elif param == "sample_rate" or param == "rbw":
                rate = float(value) * 1e6
                self.sample_rate = rate
                self.sdr.sample_rate = rate
                return f"Sample rate set to {value} MHz"
            elif param == "gain":
                self.gain = value
                self.sdr.gain = value
                return f"Gain set to {value}"
            elif param == "attenuation":
                # RTL-SDR не имеет аппаратного аттенюатора
                return f"Attenuation not supported by this device (ignored)"
            else:
                return f"Unknown parameter: {param}"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def get_info(self):
        """Получить информацию об устройстве"""
        return {
            "type": "rtl-sdr",
            "device_id": DEVICE_ID,
            "sample_rate_mhz": self.sample_rate / 1e6,
            "center_freq_mhz": self.center_freq / 1e6,
            "gain": self.gain,
            "sdr_available": self.sdr is not None
        }
    
    def close(self):
        """Закрытие SDR устройства"""
        if self.sdr:
            self.sdr.close()
            logger.info("SDR device closed")

# -------------------- MQTT Обработчики ---------------------
analyzer = RealSdrAnalyzer()

def on_connect(client, userdata, flags, rc):
    """Callback при подключении к MQTT"""
    logger.info(f"Connected to MQTT broker with code {rc}")
    client.subscribe(COMMAND_TOPIC)
    
    # Отправляем статус online
    client.publish(STATUS_TOPIC, "online")
    
    # Отправляем информацию об устройстве
    info = analyzer.get_info()
    client.publish(INFO_TOPIC, json.dumps(info))
    
    # Периодическая отправка статуса
    def send_heartbeat():
        while True:
            time.sleep(30)
            client.publish(STATUS_TOPIC, "online")
    
    heartbeat_thread = threading.Thread(target=send_heartbeat, daemon=True)
    heartbeat_thread.start()

def on_message(client, userdata, msg):
    """Callback при получении команды"""
    command = msg.payload.decode()
    logger.info(f"Received command: {command}")
    
    response = ""
    
    try:
        if command.startswith("scan_spectrum"):
            # Формат: scan_spectrum START_MHz END_MHz
            parts = command.split()
            if len(parts) >= 3:
                start_mhz = float(parts[1])
                end_mhz = float(parts[2])
            else:
                start_mhz = 88
                end_mhz = 108
            
            # Выполняем сканирование
            spectrum = analyzer.scan_spectrum(start_mhz, end_mhz)
            response = json.dumps(spectrum)
            logger.info(f"Scan complete: {len(spectrum)} points")
            
        elif command.startswith("set_"):
            # Формат: set_PARAM VALUE
            parts = command.split()
            if len(parts) >= 2:
                param = command.split("_")[1].split()[0]
                value = parts[1]
                response = analyzer.set_parameter(param, value)
            else:
                response = "Invalid command format"
                
        elif command == "get_info":
            info = analyzer.get_info()
            response = json.dumps(info)
            
        elif command == "ping":
            response = "pong"
            
        else:
            response = f"Unknown command: {command}"
            
    except Exception as e:
        response = f"Error: {str(e)}"
        logger.error(f"Command execution error: {e}")
    
    # Отправляем ответ
    client.publish(RESPONSE_TOPIC, response)
    logger.debug(f"Response sent: {response[:100]}...")

# ----------------- Запуск --------------------------
def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    
    print("=" * 60)
    print(f"📡 SDR Agent: {DEVICE_ID}")
    print("=" * 60)
    print(f"📍 MQTT Broker: {BROKER_IP}")
    print(f"📻 Device: Realtek RTL-SDR")
    print("=" * 60)
    
    try:
        client.connect(BROKER_IP, 1883, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Failed to connect: {e}")
    finally:
        analyzer.close()

if __name__ == "__main__":
    main()