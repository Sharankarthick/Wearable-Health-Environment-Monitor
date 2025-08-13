from flask import Flask, request
import paho.mqtt.client as mqtt
import json
import os
from datetime import datetime

app = Flask(__name__)

# MQTT setup
mqtt_broker = "localhost"
mqtt_port = 1883
mqtt_user = "hiotgrp1"
mqtt_password = "12341234"

def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))
    client.subscribe("health/image_metadata")
    client.subscribe("health/vitals")

def on_message(client, userdata, msg):
    if msg.topic == "health/image_metadata":
        metadata = json.loads(msg.payload.decode())
        print(f"Received image metadata: {metadata}")
    elif msg.topic == "health/vitals":
        vitals = json.loads(msg.payload.decode())
        print(f"Received vitals: {vitals}")

client = mqtt.Client()
client.username_pw_set(mqtt_user, mqtt_password)
client.on_connect = on_connect
client.on_message = on_message

client.connect(mqtt_broker, mqtt_port, 60)
client.loop_start()

@app.route('/upload', methods=['POST'])
def upload_image():
    if 'image/jpeg' not in request.headers.get('Content-Type', ''):
        return 'Invalid Content-Type', 400

    image_data = request.data
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"image_{timestamp}.jpg"
    
    os.makedirs('received_images', exist_ok=True)
    with open(f"received_images/{filename}", "wb") as f:
        f.write(image_data)
    
    print(f"Received and saved image: {filename}")
    return 'Image received', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
