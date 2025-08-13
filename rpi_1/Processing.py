#!/usr/bin/env python3
import os
import json
import time
import numpy as np
import threading
import paho.mqtt.client as mqtt
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
from flask import Flask, request, jsonify
import tensorflow as tf
import sounddevice as sd
import librosa
import cv2
from datetime import datetime
import uuid

# Flask application for handling HTTP requests
app = Flask(__name__)

# Flask routes for receiving data from ESP32
@app.route('/upload', methods=['POST'])
def upload_image():
    try:
        # Check if there's image data
        if not request.data:
            return jsonify({"error": "No image data received"}), 400
        
        # Get device ID from header or default to "unknown"
        device_id = request.headers.get('Device-ID', 'unknown')
        
        # Generate a unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{device_id}_{timestamp}_{uuid.uuid4().hex[:8]}.jpg"
        filepath = os.path.join(config["image_save_path"], filename)
        
        # Save the image
        with open(filepath, 'wb') as f:
            f.write(request.data)
        
        # Store image info in Firebase
        image_info = {
            "filename": filename,
            "device_id": device_id,
            "timestamp": int(time.time() * 1000),
            "path": filepath
        }
        db.reference(f'devices/{device_id}/images').push(image_info)
        
        print(f"Image saved: {filepath}")
        return jsonify({"status": "success", "filename": filename}), 200
    except Exception as e:
        print(f"Error saving image: {e}")
        return jsonify({"error": str(e)}), 500
        
@app.route('/process_audio', methods=['POST'])
def process_audio():
    try:
        # Check if there's audio data
        if not request.data:
            return jsonify({"error": "No audio data received"}), 400
        
        # Get device ID from header or default to "unknown"
        device_id = request.headers.get('Device-ID', 'unknown')
        
        # Save the audio data
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{device_id}_{timestamp}.wav"
        filepath = os.path.join(config["audio_save_path"], filename)
        
        # Convert bytes to numpy array (assuming 16-bit PCM)
        audio_data = np.frombuffer(request.data, dtype=np.int16)
        
        # Save audio temporarily
        with open(filepath, 'wb') as f:
            f.write(request.data)
        
        # Process audio for keyword detection
        keyword_detected = False
        detected_keyword = ""
        
        if "keyword_model" in models:
            try:
                # Normalize audio to float between -1.0 and 1.0 for Edge Impulse
                audio_float = audio_data.astype(np.float32) / 32768.0  # Normalize to [-1.0, 1.0]
                
                # Run inference with Edge Impulse model - using raw audio
                # Edge Impulse models handle feature extraction internally
                result = models["keyword_model"].classify(audio_float)
                
                # Process the result
                if result.get('result', {}).get('classification'):
                    predictions = result['result']['classification']
                    
                    # Find the keyword with the highest confidence
                    max_confidence = 0
                    detected_keyword = ""
                    max_index = 0
                    
                    for idx, (keyword, confidence) in enumerate(predictions.items()):
                        if confidence > max_confidence:
                            max_confidence = confidence
                            detected_keyword = keyword
                            max_index = idx
                    
                    confidence = max_confidence
                
                if confidence > 0.7:  # Confidence threshold
                    keyword_detected = True
                    detected_keyword = config["keywords"][max_index]
                    
                    # If keyword detected, check if we need to send an alert
                    if detected_keyword in ["help", "ouch"]:
                        alert_data = {
                            "device_id": device_id,
                            "alert_type": "keyword",
                            "keyword": detected_keyword,
                            "confidence": float(confidence),
                            "timestamp": int(time.time() * 1000)
                        }
                        
                        # Send alert to MQTT and Firebase
                        send_alert(device_id, alert_data)
                
            except Exception as e:
                print(f"Error in keyword detection: {e}")
        
        return jsonify({
            "status": "success", 
            "keyword_detected": keyword_detected,
            "keyword": detected_keyword if keyword_detected else ""
        }), 200
        
    except Exception as e:
        print(f"Error processing audio: {e}")
        return jsonify({"error": str(e)}), 500

# Global variables
models = {}
device_data = {}
config = {
    "mqtt_broker": "localhost",
    "mqtt_port": 1883,
    "mqtt_user": "hiotgrp1",
    "mqtt_password": "12341234",
    "firebase_db_url": "https://smart-healthcare-3a0d6-default-rtdb.firebaseio.com/",  # Update with your Firebase URL
    "model_paths": {
        "bpm_model": "models/bpm_model.eim",
        "spo2_model": "models/spo2_model.eim",
        "keyword_model": "models/keyword_model.eim"
    },
    "keywords": ["help", "ouch"],
    "http_server_port": 5000,
    "image_save_path": "images",
    "audio_save_path": "audio"
}

# Ensure directories exist
os.makedirs(config["image_save_path"], exist_ok=True)
os.makedirs(config["audio_save_path"], exist_ok=True)

# Import Edge Impulse module for .EIM models
try:
    import edge_impulse_linux
    from edge_impulse_linux.runner import ImpulseRunner
except ImportError:
    print("Edge Impulse SDK not installed. Run 'pip install edge_impulse_linux' to install.")
    edge_impulse_linux = None
    
 # Load machine learning models (.EIM format)
def load_models():
    print("Loading Edge Impulse ML models...")
    try:
        # Load BPM anomaly detection model
        if os.path.exists(config["model_paths"]["bpm_model"]) and edge_impulse_linux:
            models["bpm_model"] = ImpulseRunner(config["model_paths"]["bpm_model"])
            models["bpm_model"].init()
            print("BPM model loaded successfully")
        else:
            print(f"BPM model not found at {config['model_paths']['bpm_model']} or Edge Impulse SDK missing")
            
        # Load SpO2 anomaly detection model
        if os.path.exists(config["model_paths"]["spo2_model"]) and edge_impulse_linux:
            models["spo2_model"] = ImpulseRunner(config["model_paths"]["spo2_model"])
            models["spo2_model"].init()
            print("SpO2 model loaded successfully")
        else:
            print(f"SpO2 model not found at {config['model_paths']['spo2_model']} or Edge Impulse SDK missing")
            
        # Load keyword detection model
        if os.path.exists(config["model_paths"]["keyword_model"]) and edge_impulse_linux:
            models["keyword_model"] = ImpulseRunner(config["model_paths"]["keyword_model"])
            models["keyword_model"].init()
            print("Keyword model loaded successfully")
        else:
            print(f"Keyword model not found at {config['model_paths']['keyword_model']} or Edge Impulse SDK missing")
    except Exception as e:
        print(f"Error loading models: {e}")
        
# Initialize Firebase

def initialize_firebase():
    print("Initializing Firebase...")
    try:
        cred = credentials.Certificate("smart-healthcare-3a0d6-firebase-adminsdk-fbsvc-e3b80a3443.json")  # You'll need to create this file
        firebase_admin.initialize_app(cred, {
            'databaseURL': config["firebase_db_url"]
        })
        print("Firebase initialized successfully")
    except Exception as e:
        print(f"Error initializing Firebase: {e}")

# Connect to MQTT broker
def connect_mqtt():
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker!")
            client.subscribe("health/vitals")
            client.subscribe("health/parameters")
            client.subscribe("health/alerts")
            client.subscribe("health/image_metadata")
        else:
            print(f"Failed to connect to MQTT Broker. Return code: {rc}")

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            topic = msg.topic
            
            # Make sure device_id exists
            if "device_id" not in payload:
                payload["device_id"] = "unknown"
            
            device_id = payload["device_id"]
            
            # Initialize device data if not exists
            if device_id not in device_data:
                device_data[device_id] = {
                    "heart_rate": [],
                    "spo2": [],
                    "alerts": [],
                    "images": [],
                    "last_update": time.time()
                }
            
            # Process different types of messages
            if topic == "health/vitals" or topic == "health/parameters":
                process_vitals(device_id, payload)
            elif topic == "health/alerts":
                process_alert(device_id, payload)
            elif topic == "health/image_metadata":
                process_image_metadata(device_id, payload)
                
        except json.JSONDecodeError:
            print(f"Error decoding message: {msg.payload}")
        except Exception as e:
            print(f"Error processing message: {e}")

    # Create MQTT client
    client = mqtt.Client()
    client.username_pw_set(config["mqtt_user"], config["mqtt_password"])
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(config["mqtt_broker"], config["mqtt_port"], 60)
    
    return client
    
 # Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "up",
        "models_loaded": list(models.keys()),
        "active_devices": len(device_data),
        "timestamp": int(time.time())
    }), 200

# Get device status endpoint
@app.route('/device/<device_id>', methods=['GET'])
def get_device_status(device_id):
    if device_id in device_data:
        # Calculate averages
        heart_rates = device_data[device_id]["heart_rate"]
        spo2_values = device_data[device_id]["spo2"]
        
        avg_hr = sum(heart_rates) / len(heart_rates) if heart_rates else 0
        avg_spo2 = sum(spo2_values) / len(spo2_values) if spo2_values else 0
        
        return jsonify({
            "device_id": device_id,
            "last_update": device_data[device_id]["last_update"],
            "average_heart_rate": avg_hr,
            "average_spo2": avg_spo2,
            "recent_alerts": device_data[device_id]["alerts"][-5:],
            "recent_images": device_data[device_id]["images"][-5:]
        }), 200
    else:
        return jsonify({"error": "Device not found"}), 404

# Function to periodically clean up old data
def cleanup_old_data():
    while True:
        try:
            current_time = time.time()
            devices_to_remove = []
            
            # Find devices that haven't sent data in 1 hour
            for device_id, data in device_data.items():
                if current_time - data["last_update"] > 3600:  # 1 hour
                    devices_to_remove.append(device_id)
            
            # Remove inactive devices
            for device_id in devices_to_remove:
                del device_data[device_id]
                print(f"Removed inactive device: {device_id}")
            
            # Sleep for 15 minutes
            time.sleep(900)
        except Exception as e:
            print(f"Error in cleanup task: {e}")
            time.sleep(60)  # Sleep for 1 minute on error

# Send alert to MQTT and store in Firebase
def send_alert(device_id, alert_data):
    # Publish to MQTT
    client.publish("health/detected_anomalies", json.dumps(alert_data))
    
    # Store in Firebase
    db.reference(f'devices/{device_id}/alerts').push(alert_data)
    
    # Store in memory
    if len(device_data[device_id]["alerts"]) > 20:
        device_data[device_id]["alerts"].pop(0)
    device_data[device_id]["alerts"].append(alert_data)
    
    print(f"Alert sent: {alert_data}")

# Process alert from device
def process_alert(device_id, payload):
    # Store in Firebase
    db.reference(f'devices/{device_id}/alerts').push(payload)
    
    # Store in memory
    if len(device_data[device_id]["alerts"]) > 20:
        device_data[device_id]["alerts"].pop(0)
    device_data[device_id]["alerts"].append(payload)
    
    print(f"Alert received from device {device_id}: {payload}")

# Process image metadata
def process_image_metadata(device_id, payload):
    # Store metadata in Firebase
    db.reference(f'devices/{device_id}/images').push(payload)
    
    # Store in memory
    if len(device_data[device_id]["images"]) > 10:
        device_data[device_id]["images"].pop(0)
    device_data[device_id]["images"].append(payload)
    
    print(f"Image metadata received from device {device_id}: {payload}")


# Process vital signs and detect anomalies
def process_vitals(device_id, payload):
    # Extract vital signs
    heart_rate = payload.get("heart_rate", 0)
    spo2 = payload.get("spo2", 0)
    timestamp = payload.get("timestamp", int(time.time() * 1000))
    
    # Store in memory for recent history
    if len(device_data[device_id]["heart_rate"]) > 100:
        device_data[device_id]["heart_rate"].pop(0)
    if len(device_data[device_id]["spo2"]) > 100:
        device_data[device_id]["spo2"].pop(0)
    
    device_data[device_id]["heart_rate"].append(heart_rate)
    device_data[device_id]["spo2"].append(spo2)
    device_data[device_id]["last_update"] = time.time()
    
    # Detect anomalies using ML models
    if "bpm_model" in models and heart_rate > 0:
        try:
            # Prepare data for BPM model
            recent_bpm = np.array(device_data[device_id]["heart_rate"][-10:])
            if len(recent_bpm) < 10:  # Pad if needed
                recent_bpm = np.pad(recent_bpm, (10 - len(recent_bpm), 0), 'edge')
            
            # Format data for Edge Impulse model
            # Convert to float32 as required by Edge Impulse
            bpm_data = recent_bpm.astype(np.float32)
            
            # Run inference with Edge Impulse model
            result = models["bpm_model"].classify(bpm_data)
            
            # Process the result - check for anomaly class or anomaly score
            bpm_anomaly = False
            if 'anomaly' in result.get('result', {}).get('classification', {}):
                # If model directly outputs anomaly classification
                bpm_anomaly = result['result']['classification']['anomaly'] > 0.5
            elif 'anomaly' in result.get('result', {}):
                # If model outputs anomaly score
                bpm_anomaly = result['result']['anomaly'] > 0.5
            
            if bpm_anomaly:
                alert_data = {
                    "device_id": device_id,
                    "alert_type": "anomaly",
                    "source": "bpm",
                    "value": float(heart_rate),
                    "timestamp": int(time.time() * 1000)
                }
                
                # Send alert to MQTT and Firebase
                send_alert(device_id, alert_data)
        except Exception as e:
            print(f"Error in BPM anomaly detection: {e}")
    
    if "spo2_model" in models and spo2 > 0:
        try:
            # Prepare data for SpO2 model
            recent_spo2 = np.array(device_data[device_id]["spo2"][-10:])
            if len(recent_spo2) < 10:  # Pad if needed
                recent_spo2 = np.pad(recent_spo2, (10 - len(recent_spo2), 0), 'edge')
            
            # Format data for Edge Impulse model
            # Convert to float32 as required by Edge Impulse
            spo2_data = recent_spo2.astype(np.float32)
            
            # Run inference with Edge Impulse model
            result = models["spo2_model"].classify(spo2_data)
            
            # Process the result - check for anomaly class or anomaly score
            spo2_anomaly = False
            if 'anomaly' in result.get('result', {}).get('classification', {}):
                # If model directly outputs anomaly classification
                spo2_anomaly = result['result']['classification']['anomaly'] > 0.5
            elif 'anomaly' in result.get('result', {}):
                # If model outputs anomaly score
                spo2_anomaly = result['result']['anomaly'] > 0.5
            
            if spo2_anomaly:
                alert_data = {
                    "device_id": device_id,
                    "alert_type": "anomaly",
                    "source": "spo2",
                    "value": float(spo2),
                    "timestamp": int(time.time() * 1000)
                }
                
                # Send alert to MQTT and Firebase
                send_alert(device_id, alert_data)
        except Exception as e:
            print(f"Error in SpO2 anomaly detection: {e}")
    
    # Store vital data in Firebase
    try:
        vital_data = {
            "heart_rate": float(heart_rate),
            "spo2": float(spo2),
            "timestamp": timestamp
        }
        
        # Store in Firebase
        db.reference(f'devices/{device_id}/vitals').push(vital_data)
    except Exception as e:
        print(f"Error storing vitals in Firebase: {e}")
        
 # Add API endpoint to get alerts for a device
@app.route('/alerts/<device_id>', methods=['GET'])
def get_device_alerts(device_id):
    if device_id in device_data:
        # Get query parameters for time range
        start_time = request.args.get('start_time', None)
        end_time = request.args.get('end_time', None)
        
        # Filter alerts by time if provided
        alerts = device_data[device_id]["alerts"]
        if start_time and end_time:
            try:
                start = int(start_time)
                end = int(end_time)
                filtered_alerts = [
                    alert for alert in alerts 
                    if alert.get("timestamp", 0) >= start and alert.get("timestamp", 0) <= end
                ]
                return jsonify({"alerts": filtered_alerts}), 200
            except ValueError:
                return jsonify({"error": "Invalid time format"}), 400
        else:
            return jsonify({"alerts": alerts}), 200
    else:
        return jsonify({"error": "Device not found"}), 404

# Add API endpoint to get vitals history for a device
@app.route('/vitals_history/<device_id>', methods=['GET'])
def get_vitals_history(device_id):
    if device_id in device_data:
        # Return both heart rate and spo2 histories
        return jsonify({
            "device_id": device_id,
            "heart_rate": device_data[device_id]["heart_rate"],
            "spo2": device_data[device_id]["spo2"]
        }), 200
    else:
        return jsonify({"error": "Device not found"}), 404

# Main function to start the server
def main():
    print("Starting Health Monitoring Server...")
    
    # Check for Edge Impulse SDK
    if edge_impulse_linux is None:
        print("WARNING: Edge Impulse SDK is not installed. Models will not load properly.")
        print("Install with: pip install edge_impulse_linux")
    
    # Initialize Firebase
    initialize_firebase()
    
    # Load machine learning models
    load_models()
    
    # Connect to MQTT broker
    global client
    client = connect_mqtt()
    
    # Start MQTT loop in a background thread
    client.loop_start()
    
    # Start data cleanup thread
    cleanup_thread = threading.Thread(target=cleanup_old_data, daemon=True)
    cleanup_thread.start()
    
    # Start Flask server
    print(f"Starting HTTP server on port {config['http_server_port']}...")
    app.run(host='0.0.0.0', port=config['http_server_port'], debug=False, threaded=True)

if __name__ == "__main__":
    main()
