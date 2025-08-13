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
import queue
import cv2
from datetime import datetime
import uuid
import sys
import signal

# Flask application for handling HTTP requests
app = Flask(__name__)

# Global variables
models = {}
device_data = {}
processing_queue = queue.Queue()  # Queue for processing tasks
config = {
    "mqtt_broker": "localhost",
    "mqtt_port": 1883,
    "mqtt_user": "hiotgrp1",
    "mqtt_password": "12341234",
    "firebase_db_url": "https://smart-healthcare-3a0d6-default-rtdb.firebaseio.com/",
    "model_paths": {
        "bpm_model": "models/bpm_model.eim",
        "spo2_model": "models/spo2_model.eim",
        "keyword_model": "models/keyword_model.eim"
    },
    "keywords": ["help", "ouch"],
    "http_server_port": 5000,
    "image_save_path": "images",
    "audio_save_path": "audio",
    "anomaly_thresholds": {
        "bpm_high": 120,  # Define thresholds for immediate alerts
        "bpm_low": 40,
        "spo2_low": 90
    }
}

client = None  # Global MQTT client

# Ensure directories exist
os.makedirs(config["image_save_path"], exist_ok=True)
os.makedirs(config["audio_save_path"], exist_ok=True)

# Import Edge Impulse module for .EIM models
try:
    import edge_impulse_linux
    from edge_impulse_linux.runner import ImpulseRunner
    has_edge_impulse = True
except ImportError:
    print("Edge Impulse SDK not installed. Run 'pip install edge_impulse_linux' to install.")
    has_edge_impulse = False
    
# Signal handler for graceful shutdown
def signal_handler(sig, frame):
    print('Interrupted, shutting down models...')
    unload_models()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
    
# Load machine learning models (.EIM format)
def load_models():
    print("Loading Edge Impulse ML models...")
    if not has_edge_impulse:
        print("Edge Impulse SDK not available. Models will not be loaded.")
        return
        
    try:
        # Load BPM anomaly detection model
        if os.path.exists(config["model_paths"]["bpm_model"]):
            models["bpm_model"] = ImpulseRunner(config["model_paths"]["bpm_model"])
            try:
                model_info = models["bpm_model"].init()
                print(f"BPM model loaded successfully: {model_info['project']['name']}")
            except Exception as e:
                print(f"Failed to initialize BPM model: {e}")
                models["bpm_model"] = None
        else:
            print(f"BPM model not found at {config['model_paths']['bpm_model']}")
            
        # Load SpO2 anomaly detection model
        if os.path.exists(config["model_paths"]["spo2_model"]):
            models["spo2_model"] = ImpulseRunner(config["model_paths"]["spo2_model"])
            try:
                # Make the SpO2 model executable if needed
                os.chmod(config["model_paths"]["spo2_model"], 0o755)
                model_info = models["spo2_model"].init()
                print(f"SpO2 model loaded successfully: {model_info['project']['name']}")
            except Exception as e:
                print(f"Failed to initialize SpO2 model: {e}")
                models["spo2_model"] = None
        else:
            print(f"SpO2 model not found at {config['model_paths']['spo2_model']}")
            
        # Load keyword detection model
        if os.path.exists(config["model_paths"]["keyword_model"]):
            models["keyword_model"] = ImpulseRunner(config["model_paths"]["keyword_model"])
            try:
                model_info = models["keyword_model"].init()
                print(f"Keyword model loaded successfully: {model_info['project']['name']}")
            except Exception as e:
                print(f"Failed to initialize keyword model: {e}")
                models["keyword_model"] = None
        else:
            print(f"Keyword model not found at {config['model_paths']['keyword_model']}")
    except Exception as e:
        print(f"Error loading models: {e}")
        import traceback
        traceback.print_exc()

# Unload models properly
def unload_models():
    print("Unloading Edge Impulse ML models...")
    for model_name, model in models.items():
        try:
            if model:
                model.stop()
                print(f"Model {model_name} unloaded successfully")
        except Exception as e:
            print(f"Error unloading model {model_name}: {e}")
        
# Initialize Firebase
def initialize_firebase():
    print("Initializing Firebase...")
    try:
        cred = credentials.Certificate("smart-healthcare-3a0d6-firebase-adminsdk-fbsvc-e3b80a3443.json")
        firebase_admin.initialize_app(cred, {
            'databaseURL': config["firebase_db_url"]
        })
        print("Firebase initialized successfully")
    except Exception as e:
        print(f"Error initializing Firebase: {e}")

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
        filename = f"{device_id}{timestamp}{uuid.uuid4().hex[:8]}.jpg"
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
        
        # Save audio file
        with open(filepath, 'wb') as f:
            f.write(request.data)
            
        # Add to processing queue (non-blocking)
        processing_queue.put({
            'type': 'audio',
            'device_id': device_id,
            'filepath': filepath,
            'audio_data': audio_data,
            'timestamp': int(time.time() * 1000)
        })
        
        return jsonify({
            "status": "success", 
            "message": "Audio scheduled for processing"
        }), 200
        
    except Exception as e:
        print(f"Error processing audio: {e}")
        return jsonify({"error": str(e)}), 500

# Process audio for keyword detection
def process_audio_task(task):
    device_id = task['device_id']
    audio_data = task['audio_data']
    timestamp = task['timestamp']
    filepath = task['filepath']
    
    try:
        # Normalize audio to float between -1.0 and 1.0 for Edge Impulse
        audio_float = audio_data.astype(np.float32) / 32768.0  # Normalize to [-1.0, 1.0]
        
        # Store audio metadata in Firebase
        audio_info = {
            "filepath": filepath,
            "device_id": device_id,
            "timestamp": timestamp,
            "processed": False
        }
        
        audio_ref = db.reference(f'devices/{device_id}/audio').push(audio_info)
        
        # Skip processing if keyword model isn't loaded
        if "keyword_model" not in models or not models["keyword_model"]:
            print("Keyword model not available, skipping audio processing")
            return
            
        # Run inference with Edge Impulse model - using raw audio
        res = models["keyword_model"].classify(audio_float.tolist())  # Convert to list
        
        keyword_detected = False
        detected_keyword = ""
        max_confidence = 0
        
        if res["result"]["classification"]:
            # Find the keyword with the highest confidence
            for keyword, confidence in res["result"]["classification"].items():
                if confidence > max_confidence:
                    max_confidence = confidence
                    detected_keyword = keyword
            
            # Check against confidence threshold
            if max_confidence > 0.7:  # Confidence threshold
                keyword_detected = True
                
                # Map detected keyword to config keywords if needed
                matched_keyword = None
                for kw in config["keywords"]:
                    if kw.lower() in detected_keyword.lower():
                        matched_keyword = kw
                        break
                
                if matched_keyword or detected_keyword in ["help", "ouch"]:
                    alert_data = {
                        "device_id": device_id,
                        "alert_type": "keyword",
                        "keyword": matched_keyword or detected_keyword,
                        "confidence": float(max_confidence),
                        "timestamp": timestamp,
                        "audio_filepath": filepath
                    }
                    
                    # Send alert to MQTT and Firebase
                    send_alert(device_id, alert_data)
                    
                    # Update the audio entry to mark as processed with result
                    audio_ref.update({
                        "processed": True,
                        "keyword_detected": True,
                        "keyword": matched_keyword or detected_keyword,
                        "confidence": float(max_confidence)
                    })
                    
                    print(f"Keyword detected: {detected_keyword} with confidence {max_confidence}")
                    return
        
        # Update the audio entry to mark as processed with no keyword detected
        audio_ref.update({
            "processed": True,
            "keyword_detected": False
        })
        print(f"No keyword detected in audio from device {device_id}")
                
    except Exception as e:
        print(f"Error in audio processing task: {e}")
        import traceback
        traceback.print_exc()

# Connect to MQTT broker
def connect_mqtt():
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker!")
            client.subscribe("health/vitals/#")
            client.subscribe("health/parameters/#")
            client.subscribe("health/alerts/#")
            client.subscribe("health/image_metadata/#")
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
            if topic.startswith("health/vitals") or topic.startswith("health/parameters"):
                # Add to processing queue
                processing_queue.put({
                    'type': 'vitals',
                    'device_id': device_id,
                    'payload': payload
                })
            elif topic.startswith("health/alerts"):
                process_alert(device_id, payload)
            elif topic.startswith("health/image_metadata"):
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
    
    try:
        client.connect(config["mqtt_broker"], config["mqtt_port"], 60)
        print("Connected to MQTT broker")
    except Exception as e:
        print(f"Error connecting to MQTT broker: {e}")
    
    return client
    
# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "up",
        "models_loaded": [name for name, model in models.items() if model is not None],
        "active_devices": len(device_data),
        "queue_size": processing_queue.qsize(),
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
        
        # Get latest values
        latest_hr = heart_rates[-1] if heart_rates else 0
        latest_spo2 = spo2_values[-1] if spo2_values else 0
        
        return jsonify({
            "device_id": device_id,
            "last_update": device_data[device_id]["last_update"],
            "latest_heart_rate": latest_hr,
            "latest_spo2": latest_spo2,
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
    # Ensure alert has all required fields
    if "timestamp" not in alert_data:
        alert_data["timestamp"] = int(time.time() * 1000)
        
    # Publish to MQTT
    if client:
        client.publish("health/detected_anomalies", json.dumps(alert_data))
    
    # Store in Firebase
    alert_ref = db.reference(f'devices/{device_id}/alerts').push(alert_data)
    
    # Store in memory
    if device_id not in device_data:
        device_data[device_id] = {
            "heart_rate": [],
            "spo2": [],
            "alerts": [],
            "images": [],
            "last_update": time.time()
        }
        
    if len(device_data[device_id]["alerts"]) > 20:
        device_data[device_id]["alerts"].pop(0)
    device_data[device_id]["alerts"].append(alert_data)
    
    print(f"Alert sent: {alert_data}")
    
    # Return the Firebase reference key
    return alert_ref.key

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
def process_vitals_task(task):
    device_id = task['device_id']
    payload = task['payload']
    
    # Extract vital signs
    heart_rate = payload.get("heart_rate", 0)
    spo2 = payload.get("spo2", 0)
    timestamp = payload.get("timestamp", int(time.time() * 1000))
    
    # Basic validation
    if heart_rate <= 0 and spo2 <= 0:
        print(f"Invalid vital signs from device {device_id}: HR={heart_rate}, SpO2={spo2}")
        return
    
    # Store in memory for recent history
    if len(device_data[device_id]["heart_rate"]) > 100:
        device_data[device_id]["heart_rate"].pop(0)
    if len(device_data[device_id]["spo2"]) > 100:
        device_data[device_id]["spo2"].pop(0)
    
    if heart_rate > 0:
        device_data[device_id]["heart_rate"].append(heart_rate)
    if spo2 > 0:
        device_data[device_id]["spo2"].append(spo2)
        
    device_data[device_id]["last_update"] = time.time()
    
    # First check for immediate threshold-based anomalies
    if heart_rate > 0:
        if heart_rate > config["anomaly_thresholds"]["bpm_high"]:
            alert_data = {
                "device_id": device_id,
                "alert_type": "threshold",
                "source": "bpm_high",
                "value": float(heart_rate),
                "threshold": config["anomaly_thresholds"]["bpm_high"],
                "timestamp": timestamp
            }
            send_alert(device_id, alert_data)
            print(f"BPM high threshold alert: {heart_rate} > {config['anomaly_thresholds']['bpm_high']}")
            
        elif heart_rate < config["anomaly_thresholds"]["bpm_low"]:
            alert_data = {
                "device_id": device_id,
                "alert_type": "threshold",
                "source": "bpm_low",
                "value": float(heart_rate),
                "threshold": config["anomaly_thresholds"]["bpm_low"],
                "timestamp": timestamp
            }
            send_alert(device_id, alert_data)
            print(f"BPM low threshold alert: {heart_rate} < {config['anomaly_thresholds']['bpm_low']}")
    
    if spo2 > 0 and spo2 < config["anomaly_thresholds"]["spo2_low"]:
        alert_data = {
            "device_id": device_id,
            "alert_type": "threshold",
            "source": "spo2_low",
            "value": float(spo2),
            "threshold": config["anomaly_thresholds"]["spo2_low"],
            "timestamp": timestamp
        }
        send_alert(device_id, alert_data)
        print(f"SpO2 low threshold alert: {spo2} < {config['anomaly_thresholds']['spo2_low']}")
    
    # Then run ML-based anomaly detection if we have enough data points
    detect_bpm_anomaly(device_id, heart_rate, timestamp)
    detect_spo2_anomaly(device_id, spo2, timestamp)
    
    # Store vital data in Firebase
    try:
        vital_data = {
            "timestamp": timestamp
        }
        
        if heart_rate > 0:
            vital_data["heart_rate"] = float(heart_rate)
        if spo2 > 0:
            vital_data["spo2"] = float(spo2)
        
        # Store in Firebase
        db.reference(f'devices/{device_id}/vitals').push(vital_data)
    except Exception as e:
        print(f"Error storing vitals in Firebase: {e}")

# Detect BPM anomalies
def detect_bpm_anomaly(device_id, heart_rate, timestamp):
    if heart_rate <= 0 or "bpm_model" not in models or not models["bpm_model"]:
        return
        
    try:
        # We need at least a few data points for meaningful detection
        if len(device_data[device_id]["heart_rate"]) < 5:
            return
            
        # Prepare data for BPM model - use only the 2 features the model expects
        # Feature 1: Current heart rate
        # Feature 2: Average of recent heart rates (excluding current)
        recent_bpm = device_data[device_id]["heart_rate"][-10:]
        avg_recent_bpm = sum(recent_bpm[:-1]) / len(recent_bpm[:-1]) if len(recent_bpm) > 1 else heart_rate
        
        # Format data for Edge Impulse model - only 2 features as expected
        bpm_data = [float(heart_rate), float(avg_recent_bpm)]
        
        # Run inference with Edge Impulse model
        res = models["bpm_model"].classify(bpm_data)
        
        # Process the result based on the model output format
        bpm_anomaly = False
        anomaly_score = 0
        
        # Check if there's a direct anomaly score
        if "anomaly" in res["result"]:
            anomaly_score = res["result"]["anomaly"]
            bpm_anomaly = anomaly_score > 0.5  # Threshold
        # Or if it's in the classification dict
        elif "classification" in res["result"] and "anomaly" in res["result"]["classification"]:
            anomaly_score = res["result"]["classification"]["anomaly"]
            bpm_anomaly = anomaly_score > 0.5  # Threshold
        
        if bpm_anomaly:
            alert_data = {
                "device_id": device_id,
                "alert_type": "anomaly",
                "source": "bpm",
                "value": float(heart_rate),
                "anomaly_score": float(anomaly_score),
                "timestamp": timestamp
            }
            
            # Send alert to MQTT and Firebase
            send_alert(device_id, alert_data)
            print(f"BPM anomaly detected: {heart_rate} (score: {anomaly_score})")
    except Exception as e:
        print(f"Error in BPM anomaly detection: {e}")
        import traceback
        traceback.print_exc()

# Detect SpO2 anomalies
def detect_spo2_anomaly(device_id, spo2, timestamp):
    if spo2 <= 0 or "spo2_model" not in models or not models["spo2_model"]:
        return
        
    try:
        # We need at least a few data points for meaningful detection
        if len(device_data[device_id]["spo2"]) < 5:
            return
            
        # Prepare data for SpO2 model - use only the 2 features the model expects
        # Feature 1: Current SpO2
        # Feature 2: Average of recent SpO2 (excluding current)
        recent_spo2 = device_data[device_id]["spo2"][-10:]
        avg_recent_spo2 = sum(recent_spo2[:-1]) / len(recent_spo2[:-1]) if len(recent_spo2) > 1 else spo2
        
        # Format data for Edge Impulse model - only 2 features as expected
        spo2_data = [float(spo2), float(avg_recent_spo2)]
        
        # Run inference with Edge Impulse model
        res = models["spo2_model"].classify(spo2_data)
        
        # Process the result based on the model output format
        spo2_anomaly = False
        anomaly_score = 0
        
        # Check if there's a direct anomaly score
        if "anomaly" in res["result"]:
            anomaly_score = res["result"]["anomaly"]
            spo2_anomaly = anomaly_score > 0.5  # Threshold
        # Or if it's in the classification dict
        elif "classification" in res["result"] and "anomaly" in res["result"]["classification"]:
            anomaly_score = res["result"]["classification"]["anomaly"]
            spo2_anomaly = anomaly_score > 0.5  # Threshold
        
        if spo2_anomaly:
            alert_data = {
                "device_id": device_id,
                "alert_type": "anomaly",
                "source": "spo2",
                "value": float(spo2),
                "anomaly_score": float(anomaly_score),
                "timestamp": timestamp
            }
            
            # Send alert to MQTT and Firebase
            send_alert(device_id, alert_data)
            print(f"SpO2 anomaly detected: {spo2} (score: {anomaly_score})")
    except Exception as e:
        print(f"Error in SpO2 anomaly detection: {e}")
        import traceback
        traceback.print_exc()
        
# Task processor thread
def task_processor():
    print("Starting task processor thread...")
    while True:
        try:
            # Get a task from the queue
            task = processing_queue.get(block=True, timeout=1)
            
            # Process based on task type
            if task['type'] == 'audio':
                process_audio_task(task)
            elif task['type'] == 'vitals':
                process_vitals_task(task)
                
            # Mark task as done
            processing_queue.task_done()
            
        except queue.Empty:
            # No tasks available, just continue
            pass
        except Exception as e:
            print(f"Error processing task: {e}")
            import traceback
            traceback.print_exc()
            
            # Mark task as done even on error
            try:
                processing_queue.task_done()
            except:
                pass
                
            # Sleep a bit after an error
            time.sleep(1)
            
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
        # Get query parameters for time range
        start_time = request.args.get('start_time', None)
        end_time = request.args.get('end_time', None)
        limit = request.args.get('limit', None)
        
        # Get data from device
        heart_rates = device_data[device_id]["heart_rate"]
        spo2_values = device_data[device_id]["spo2"]
        
        # Apply limit if provided
        if limit:
            try:
                l = int(limit)
                heart_rates = heart_rates[-l:]
                spo2_values = spo2_values[-l:]
            except ValueError:
                return jsonify({"error": "Invalid limit parameter"}), 400
        
        # Return data
        return jsonify({
            "device_id": device_id,
            "heart_rate": heart_rates,
            "spo2": spo2_values,
            "last_update": device_data[device_id]["last_update"]
        }), 200
    else:
        return jsonify({"error": "Device not found"}), 404

# Main function to start the server
def main():
    print("Starting Health Monitoring Server...")
    
    # Initialize Firebase
    initialize_firebase()
    
    # Load Edge Impulse ML models
    load_models()
    
    # Connect to MQTT broker
    global client
    client = connect_mqtt()
    
    # Start MQTT loop in a separate thread
    mqtt_thread = threading.Thread(target=client.loop_forever)
    mqtt_thread.daemon = True
    mqtt_thread.start()
    
    # Start task processor thread
    processor_thread = threading.Thread(target=task_processor)
    processor_thread.daemon = True
    processor_thread.start()
    
    # Start cleanup thread
    cleanup_thread = threading.Thread(target=cleanup_old_data)
    cleanup_thread.daemon = True
    cleanup_thread.start()
    
    print(f"Starting HTTP server on port {config['http_server_port']}...")
    
    # Start Flask application
    app.run(host='0.0.0.0', port=config['http_server_port'], debug=False, threaded=True)
    
    # Unload models on exit (though this may not execute depending on how the app is terminated)
    unload_models()

# Add this line to make the script runnable
if __name__ == "__main__":
    main()
