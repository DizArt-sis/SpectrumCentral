import paho.mqtt.client as mqtt
import subprocess
import random
import json

BROKER_IP = "192.168.1.11" # Broker's IP address
DEVICE_ID = "device1" # Device number

COMMAND_TOPIC = f"devices/{DEVICE_ID}/commands"
RESPONSE_TOPIC = f"devices/{DEVICE_ID}/response"

def generate_spectrum(start_freq, end_freq):
    spectrum = []

    # фиксированные "сигналы"
    signal_freqs = [
        start_freq + (end_freq - start_freq) * 0.2,
        start_freq + (end_freq - start_freq) * 0.5,
        start_freq + (end_freq - start_freq) * 0.8,
    ]

    for freq in range(start_freq, end_freq):
        noise = random.randint(-90, -70)

        # если рядом с сигналом → усиливаем
        if any(abs(freq - int(sf)) < 2 for sf in signal_freqs):
            power = random.randint(-50, -30)
        else:
            power = noise

        spectrum.append({"freq": freq, "power": power})

    return spectrum


def on_connect(client, userdata, flags, rc):
    print("Connected to broker")
    client.subscribe(COMMAND_TOPIC)


def on_message(client, userdata, msg):
    command = msg.payload.decode()
    print(f"Received command: {command}")

    if command.startswith("scan_spectrum"):
        try:
            _, start, end = command.split()
            start = int(start)
            end = int(end)
        except:
            start, end = 500, 600

        spectrum = generate_spectrum(start, end)
        response = json.dumps(spectrum)

    elif command == "get_metrics":
        result = subprocess.check_output("uptime", shell=True)
        response = result.decode()

    else:
        try:
            result = subprocess.check_output(command, shell=True)
            response = result.decode()
        except Exception as e:
            response = str(e)

    client.publish(RESPONSE_TOPIC, response)


client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER_IP, 1883, 60)
client.loop_forever()