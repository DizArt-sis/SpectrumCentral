from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import paho.mqtt.client as mqtt
import time

app = FastAPI()

BROKER_IP = "192.168.1.11" # Broker's IP address

mqtt_client = mqtt.Client()
mqtt_client.connect(BROKER_IP, 1883, 60)

responses = {}

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode()
    device_id = topic.split("/")[1]
    responses[device_id] = payload

mqtt_client.on_message = on_message
mqtt_client.subscribe("devices/+/response")
mqtt_client.loop_start()


@app.get("/send_command")
def send_command(device: str, cmd: str):
    topic = f"devices/{device}/commands"
    mqtt_client.publish(topic, cmd)

    timeout = 5
    start = time.time()

    while time.time() - start < timeout:
        if device in responses:
            return {"device": device, "response": responses.pop(device)}

    return {"error": "No response"}


@app.get("/", response_class=HTMLResponse)
def index():
    with open("index.html") as f:
        return f.read()