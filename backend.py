#!/usr/bin/env python3
"""
RF Spectrum Control System - Backend Server
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from paho.mqtt import client as mqtt
from datetime import datetime
from typing import Dict, Optional, List
import asyncio
import json
import sqlite3
import threading
import logging
import os

# --------------------- Конфигурация ---------------------------------
BROKER_IP = "127.0.0.1"  # Измените на IP вашего MQTT брокера
MQTT_PORT = 1883
HISTORY_LIMIT = 100

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ---------------------- Инициализация БД ----------------------------
def init_database():
    """Инициализация базы данных SQLite"""
    conn = sqlite3.connect("measurements.db")
    cursor = conn.cursor()

    # Таблица измерений
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            start_freq REAL,
            end_freq REAL,
            data TEXT NOT NULL,
            max_power REAL,
            avg_power REAL,
            num_signals INTEGER
        )
    """)

    # Таблица устройств
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id TEXT PRIMARY KEY,
            last_seen TEXT NOT NULL,
            status TEXT DEFAULT 'offline',
            device_type TEXT DEFAULT 'unknown'
        )
    """)

    # Таблица тревог (алертов)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            frequency REAL,
            power REAL,
            threshold REAL,
            message TEXT,
            is_resolved INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()
    logger.info("Database initialized")


init_database()


# -------------------- MQTT Менеджер ------------------------------
class MQTTManager:
    """Управление MQTT соединениями и командами"""

    def __init__(self):
        self.client = mqtt.Client()
        self.responses: Dict[str, str] = {}
        self.device_status: Dict[str, bool] = {}
        self.device_type: Dict[str, str] = {}
        self.response_events: Dict[str, threading.Event] = {}
        self.lock = threading.Lock()

    def connect(self):
        """Подключение к MQTT брокеру"""
        self.client.on_message = self.on_message
        self.client.on_connect = self.on_connect
        self.client.connect(BROKER_IP, MQTT_PORT, 60)
        self.client.loop_start()
        logger.info(f"MQTT connecting to {BROKER_IP}:{MQTT_PORT}")

    def on_connect(self, client, userdata, flags, rc):
        """Callback при подключении"""
        logger.info(f"MQTT connected with code {rc}")
        client.subscribe("devices/+/response")
        client.subscribe("devices/+/status")
        client.subscribe("devices/+/info")

    def on_message(self, client, userdata, msg):
        """Callback при получении сообщения"""
        topic = msg.topic
        payload = msg.payload.decode()

        logger.debug(f"MQTT received: {topic} -> {payload[:100]}")

        if "/response" in topic:
            device_id = topic.split("/")[1]
            with self.lock:
                self.responses[device_id] = payload
                if device_id in self.response_events:
                    self.response_events[device_id].set()

        elif "/status" in topic:
            device_id = topic.split("/")[1]
            is_online = payload == "online"
            self.device_status[device_id] = is_online

            # Обновляем статус в БД
            conn = sqlite3.connect("measurements.db")
            conn.execute(
                "INSERT OR REPLACE INTO devices (id, last_seen, status, device_type) VALUES (?, ?, ?, COALESCE((SELECT device_type FROM devices WHERE id=?), ?))",
                (
                    device_id,
                    datetime.now().isoformat(),
                    "online" if is_online else "offline",
                    device_id,
                    "unknown",
                ),
            )
            conn.commit()
            conn.close()
            logger.info(
                f"Device {device_id} status: {'online' if is_online else 'offline'}"
            )

        elif "/info" in topic:
            device_id = topic.split("/")[1]
            try:
                info = json.loads(payload)
                device_type = info.get("type", "unknown")
                self.device_type[device_id] = device_type
                logger.info(f"Device {device_id} type: {device_type}")
            except:
                pass

    def send_command(
        self, device: str, command: str, timeout: int = 10
    ) -> Optional[str]:
        """Отправка команды устройству и ожидание ответа"""
        if not self.device_status.get(device, False):
            logger.warning(f"Device {device} is offline")
            return None

        topic = f"devices/{device}/commands"

        with self.lock:
            self.response_events[device] = threading.Event()
            self.responses.pop(device, None)

        self.client.publish(topic, command)
        logger.info(f"Command sent to {device}: {command}")

        if self.response_events[device].wait(timeout):
            with self.lock:
                response = self.responses.get(device)
                self.response_events.pop(device, None)
                return response

        with self.lock:
            self.response_events.pop(device, None)
        logger.error(f"Timeout waiting for response from {device}")
        return None

    def get_device_status(self, device: str) -> bool:
        """Получить статус устройства"""
        return self.device_status.get(device, False)

    def get_devices(self) -> List[Dict]:
        """Получить список всех устройств"""
        conn = sqlite3.connect("measurements.db")
        cursor = conn.execute(
            "SELECT id, status, last_seen, device_type FROM devices ORDER BY last_seen DESC"
        )
        devices = []
        for row in cursor.fetchall():
            devices.append(
                {
                    "id": row[0],
                    "status": row[1],
                    "online": self.device_status.get(row[0], False),
                    "last_seen": row[2],
                    "type": row[3] or self.device_type.get(row[0], "unknown"),
                }
            )
        conn.close()
        return devices


# Глобальный экземпляр MQTT менеджера
mqtt_manager = MQTTManager()

# ------------------------ FastAPI Приложение --------------------------
app = FastAPI(title="RF Spectrum Control System", version="2.0")

# CORS настройки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Запуск MQTT при старте
@app.on_event("startup")
async def startup_event():
    mqtt_manager.connect()


# ---------------------- API Эндпоинты ---------------------


@app.get("/", response_class=HTMLResponse)
async def get_index():
    """Главная страница"""
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("<h1>index.html not found</h1>", status_code=404)


@app.get("/api/devices")
async def get_devices():
    """Получить список всех устройств"""
    return {"devices": mqtt_manager.get_devices()}


@app.get("/api/scan")
async def scan_spectrum(device: str, start_freq: float, end_freq: float):
    """
    Запустить сканирование спектра
    start_freq, end_freq в MHz
    """
    # Проверяем статус устройства
    if not mqtt_manager.get_device_status(device):
        raise HTTPException(status_code=404, detail=f"Device {device} is offline")

    # Формируем команду (частоты в MHz)
    command = f"scan_spectrum {start_freq} {end_freq}"
    response = mqtt_manager.send_command(device, command, timeout=15)

    if response is None:
        raise HTTPException(status_code=408, detail="Device timeout - no response")

    try:
        # Парсим ответ
        spectrum_data = json.loads(response)

        if not isinstance(spectrum_data, list):
            raise ValueError("Invalid spectrum data format")

        # Вычисляем статистику
        powers = [
            p["power"] for p in spectrum_data if isinstance(p, dict) and "power" in p
        ]
        max_power = max(powers) if powers else -100
        avg_power = sum(powers) / len(powers) if powers else -100
        num_signals = len([p for p in powers if p > -60])

        # Сохраняем в БД
        conn = sqlite3.connect("measurements.db")
        conn.execute(
            """INSERT INTO measurements 
               (device, timestamp, start_freq, end_freq, data, max_power, avg_power, num_signals) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                device,
                datetime.now().isoformat(),
                start_freq,
                end_freq,
                json.dumps(spectrum_data),
                max_power,
                avg_power,
                num_signals,
            ),
        )
        conn.commit()
        conn.close()

        # Проверяем на тревоги (сигналы сильнее -40 dBm)
        for point in spectrum_data:
            if point.get("power", -100) > -40:
                conn = sqlite3.connect("measurements.db")
                conn.execute(
                    """INSERT INTO alerts 
                       (device, timestamp, frequency, power, threshold, message, is_resolved) 
                       VALUES (?, ?, ?, ?, ?, ?, 0)""",
                    (
                        device,
                        datetime.now().isoformat(),
                        point["freq"],
                        point["power"],
                        -40,
                        f"⚠️ Сильный сигнал на {point['freq']:.1f} MHz ({point['power']:.1f} dBm)",
                    ),
                )
                conn.commit()
                conn.close()
                logger.warning(
                    f"Alert: {device} - strong signal at {point['freq']} MHz"
                )

        return {
            "device": device,
            "spectrum": spectrum_data,
            "max_power": round(max_power, 1),
            "avg_power": round(avg_power, 1),
            "num_signals": num_signals,
            "timestamp": datetime.now().isoformat(),
        }

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}, response: {response[:200]}")
        raise HTTPException(
            status_code=500, detail=f"Invalid response from device: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Scan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/history")
async def get_history(device: Optional[str] = None, limit: int = 50):
    """Получить историю измерений"""
    conn = sqlite3.connect("measurements.db")
    conn.row_factory = sqlite3.Row

    if device:
        cursor = conn.execute(
            "SELECT * FROM measurements WHERE device = ? ORDER BY timestamp DESC LIMIT ?",
            (device, min(limit, HISTORY_LIMIT)),
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM measurements ORDER BY timestamp DESC LIMIT ?",
            (min(limit, HISTORY_LIMIT),),
        )

    measurements = [dict(row) for row in cursor.fetchall()]
    # Преобразуем data из JSON строки обратно в объект
    for m in measurements:
        if isinstance(m.get("data"), str):
            try:
                m["data"] = json.loads(m["data"])
            except:
                pass

    conn.close()
    return {"measurements": measurements}


@app.get("/api/alerts")
async def get_alerts(
    device: Optional[str] = None, resolved: bool = False, limit: int = 50
):
    """Получить список тревог"""
    conn = sqlite3.connect("measurements.db")
    conn.row_factory = sqlite3.Row

    query = "SELECT * FROM alerts WHERE is_resolved = ?"
    params = [1 if resolved else 0]

    if device:
        query += " AND device = ?"
        params.append(device)

    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(min(limit, 100))

    cursor = conn.execute(query, params)
    alerts = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"alerts": alerts}


@app.post("/api/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: int):
    """Отметить тревогу как решенную"""
    conn = sqlite3.connect("measurements.db")
    conn.execute("UPDATE alerts SET is_resolved = 1 WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()
    return {"status": "resolved"}


@app.get("/api/export/{measurement_id}")
async def export_measurement(measurement_id: int):
    """Экспорт измерения в CSV"""
    conn = sqlite3.connect("measurements.db")
    cursor = conn.execute(
        "SELECT device, start_freq, end_freq, data, timestamp FROM measurements WHERE id = ?",
        (measurement_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Measurement not found")

    device, start_freq, end_freq, data, timestamp = row

    try:
        spectrum = json.loads(data) if isinstance(data, str) else data
    except:
        spectrum = []

    # Создаем CSV
    csv_content = f"# Spectrum Measurement Export\n"
    csv_content += f"# Device: {device}\n"
    csv_content += f"# Time: {timestamp}\n"
    csv_content += f"# Range: {start_freq}-{end_freq} MHz\n"
    csv_content += "#\n"
    csv_content += "Frequency (MHz),Power (dBm)\n"

    for point in spectrum:
        csv_content += f"{point.get('freq', 0)},{point.get('power', -100)}\n"

    # Сохраняем временный файл
    filename = (
        f"export_{measurement_id}_{timestamp.replace(':', '-').replace(' ', '_')}.csv"
    )
    with open(filename, "w", encoding="utf-8") as f:
        f.write(csv_content)

    return FileResponse(
        filename,
        media_type="text/csv",
        filename=filename,
        background=lambda: os.remove(filename),  # Удаляем после отправки
    )


@app.get("/api/device/configure")
async def configure_device(
    device: str,
    rbw: Optional[float] = None,
    attenuation: Optional[int] = None,
    center_freq: Optional[float] = None,
    span: Optional[float] = None,
    gain: Optional[str] = None,
):
    """Настройка параметров устройства"""
    if not mqtt_manager.get_device_status(device):
        raise HTTPException(status_code=404, detail=f"Device {device} is offline")

    commands = []

    if rbw is not None:
        commands.append(f"set_rbw {rbw}")
    if attenuation is not None:
        commands.append(f"set_attenuation {attenuation}")
    if center_freq is not None:
        commands.append(f"set_center_freq {center_freq}")
    if span is not None:
        commands.append(f"set_span {span}")
    if gain is not None:
        commands.append(f"set_gain {gain}")

    if not commands:
        return {"device": device, "message": "No parameters to set", "results": []}

    results = []
    for cmd in commands:
        response = mqtt_manager.send_command(device, cmd, timeout=5)
        results.append({"command": cmd, "response": response})
        if response is None:
            logger.warning(f"Command failed: {cmd}")

    return {"device": device, "results": results}


# WebSocket для реального времени
@app.websocket("/ws/{device}")
async def websocket_endpoint(websocket: WebSocket, device: str):
    await websocket.accept()
    try:
        while True:
            if mqtt_manager.get_device_status(device):
                await websocket.send_json({"status": "online", "device": device})
            else:
                await websocket.send_json({"status": "offline", "device": device})
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for {device}")


# -------------------- Запуск ---------------------------
if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("🎛️  RF Spectrum Control System - Backend Server")
    print("=" * 60)
    print(f"📍 MQTT Broker: {BROKER_IP}:{MQTT_PORT}")
    print(f"🌐 Web Interface: http://localhost:8000")
    print(f"📡 API Docs: http://localhost:8000/docs")
    print("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=8000)
