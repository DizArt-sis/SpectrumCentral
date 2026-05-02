📖 О проекте
RF Spectrum Control System - это дипломный проект, представляющий собой централизованную систему для управления распределенными анализаторами радиочастотного спектра. Система поддерживает как реальные SDR устройства (RTL-SDR), так и программные эмуляторы для тестирования.

🎯 Основные возможности
✅ Управление несколькими анализаторами через единый веб-интерфейс

✅ Реальное время - отображение спектра с обновлением каждые 2-3 секунды

✅ Поддержка RTL-SDR - работа с реальными SDR устройствами

✅ Эмулятор - тестовый режим без физического оборудования

✅ Автоматическое обнаружение сигналов с пороговыми значениями

✅ Система оповещений при превышении уровня мощности

✅ Сохранение истории всех измерений в SQLite

✅ Экспорт данных в CSV формат

✅ Визуализация интерактивных графиков с Chart.js

✅ Адаптивный веб-интерфейс для любых устройств

🏗 Архитектура системы

┌─────────────────────────────────────────────────────────────────┐
│                         Web Browser                              │
│                    (http://localhost:8000)                       │
└─────────────────────────────┬───────────────────────────────────┘
                              │ REST API / WebSocket
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                             │
│                   (Python + Uvicorn)                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  REST API   │  │  WebSocket  │  │   SQLite    │              │
│  │  Endpoints  │  │   Server    │  │  Database   │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────┬───────────────────────────────────┘
                              │ MQTT Protocol
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        MQTT Broker                               │
│                     (Mosquitto/Eclipse)                          │
└─────────────┬───────────────────────────────┬───────────────────┘
              │                               │
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│   Real SDR Agent        │     │   Emulator Agent        │
│   (RTL-SDR Hardware)    │     │   (Software Only)       │
├─────────────────────────┤     ├─────────────────────────┤
│ • Realtek RTL2832U      │     │ • Signal generation     │
│ • 24-1700 MHz range     │     │ • Noise simulation      │
│ • Automatic gain        │     │ • Peak detection        │
│ • Spectrum scanning     │     │ • Configurable params   │
└─────────────────────────┘     └─────────────────────────┘

📁 Структура проекта
rf-spectrum-control-system/
│
├── backend.py                 # FastAPI сервер (ядро системы)
├── agent_sdr.py              # Реальный SDR агент (RTL-SDR)
├── agent_emulator.py         # Эмулятор для тестирования
├── index.html                # Веб-интерфейс
├── requirements.txt          # Python зависимости
├── README.md                 # Документация

🚀 Быстрый старт
Требования
Python 3.8 или выше

MQTT брокер (Mosquitto)

(Опционально) RTL-SDR устройство
Установка
# 1. Клонирование репозитория
git clone https://github.com/yourusername/rf-spectrum-control-system.git
cd rf-spectrum-control-system

# 2. Создание виртуального окружения
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3. Установка зависимостей
pip install -r requirements.txt

# 4. Установка MQTT брокера (Ubuntu/Debian)
sudo apt-get install mosquitto mosquitto-clients
sudo systemctl start mosquitto

# 5. (Опционально) Установка драйверов для RTL-SDR
sudo apt-get install rtl-sdr
