#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include "MAX30100_PulseOximeter.h"
#include <U8g2lib.h>
#include <SPI.h>
#include "esp_camera.h"
#include "FS.h"
#include "SD.h"
#include <ArduinoJson.h>
#include <base64.h>
#include <HTTPClient.h>
#include "ESP_I2S.h"

// Create an instance of the I2SClass
I2SClass i2s;

#define CAMERA_MODEL_XIAO_ESP32S3
#include "camera_pins.h"

// WiFi and MQTT configuration
const char* ssid = "Spidy";
const char* password = "skwgpcgr";
const char* mqttServer = "192.168.58.116";
const int mqttPort = 1883;
const char* mqttUser = "hiotgrp1";
const char* mqttPassword = "12341234";

// MAX30100 configuration
#define REPORTING_PERIOD_MS 5000
#define SDA_PIN 5
#define SCL_PIN 6

// I2S PDM microphone pins for XIAO ESP32S3 Sense
#define I2S_WS 42  // LRCK
#define I2S_SD 41  // DATA

// SOS Button pin - Define the GPIO pin for the SOS button
#define SOS_BUTTON_PIN 1  // Replace with your actual GPIO pin
#define DEBOUNCE_TIME 200  // Debounce time in milliseconds

// Time intervals
#define IMAGE_CAPTURE_INTERVAL 30000 // Capture image every 30 seconds
#define AUDIO_CAPTURE_INTERVAL 30000 // Record audio every 30 seconds
#define AUDIO_RECORD_DURATION 5      // Record 5 seconds of audio
#define AUDIO_SAMPLE_RATE 16000      // Audio sample rate in Hz
#define ANIMATION_INTERVAL 250       // Animation frame update interval (ms)

// Status flags
bool camera_sign = false;
bool sd_sign = false;

// Time tracking
unsigned long lastCaptureTime = 0;
unsigned long lastAudioCaptureTime = 0;
unsigned long lastAnimationTime = 0;
uint32_t tsLastReport = 0;
int imageCount = 0;
unsigned long lastButtonTime = 0;  // For button debouncing
int audioFileCounter = 0;  // Counter for audio files

// Display power management
unsigned long lastActivityTime = 0;
const unsigned long SCREEN_TIMEOUT = 30000; // Turn off display after inactivity

// Device identifier - This should be unique for each wearable
const char* DEVICE_ID = "wearable_001";

// Audio processing flags
bool audioProcessingActive = false;
bool keywordDetected = false;
String detectedKeyword = "";

// Assistant character states
enum AssistantState {
  NORMAL,
  HAPPY,
  THINKING,
  ALERT,
  RECORDING,
  LOADING
};

AssistantState currentState = NORMAL;
uint8_t animationFrame = 0;
String statusMessage = "";
String infoMessage = "";
unsigned long messageDisplayTime = 0;
const unsigned long MESSAGE_DISPLAY_DURATION = 3000; // How long messages display (ms)

WiFiClient espClient;
PubSubClient client(espClient);
PulseOximeter pox;

U8G2_SSD1327_MIDAS_128X128_F_4W_HW_SPI u8g2(U8G2_R0, 2, 44, 43);

// Function declarations
void updateAssistantDisplay();
void setAssistantState(AssistantState state);
void showMessage(String status, String info);

// Callback for beat detection
void onBeatDetected() {
    Serial.println("Beat detected!");
    // Flash the assistant briefly to happy state when heartbeat detected
    setAssistantState(HAPPY);
    lastActivityTime = millis();
}

void callback(char* topic, byte* payload, unsigned int length) {
  Serial.print("Message arrived in topic: ");
  Serial.println(topic);
  Serial.print("Message:");
  String message = "";
  for (int i = 0; i < length; i++) {
    Serial.print((char)payload[i]);
    message += (char)payload[i];
  }
  Serial.println();
  Serial.println("-----------------------");
  
  // Show the message on display
  showMessage("New Message", message.substring(0, 20));
}

void reconnectMQTT() {
    setAssistantState(THINKING);
    showMessage("MQTT", "Reconnecting...");
    
    while (!client.connected()) {
        Serial.println("Attempting MQTT connection...");
        if (client.connect("ESP32Client", mqttUser, mqttPassword)) {
            Serial.println("Connected to MQTT broker");
            client.subscribe("health/commands");
            showMessage("MQTT", "Connected!");
            setAssistantState(HAPPY);
        } else {
            Serial.print("Failed, rc=");
            Serial.print(client.state());
            Serial.println(" Retrying in 5 seconds");
            showMessage("MQTT", "Failed, retrying...");
            setAssistantState(ALERT);
            delay(5000);
        }
    }
}

void setupCamera() {
  setAssistantState(THINKING);
  showMessage("Camera", "Initializing...");
  
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.frame_size = FRAMESIZE_UXGA;
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 12;
  config.fb_count = 1;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x", err);
    showMessage("Camera", "Init failed!");
    setAssistantState(ALERT);
    return;
  }
  camera_sign = true;
  showMessage("Camera", "Ready!");
  setAssistantState(HAPPY);
}

void uploadImageHTTP(camera_fb_t *fb) {
  setAssistantState(LOADING);
  showMessage("Camera", "Uploading image...");
  
  HTTPClient http;
  http.begin("http://192.168.58.116:5000/upload"); // Replace with your RPi's IP and port
  http.addHeader("Content-Type", "image/jpeg");
  
  int httpResponseCode = http.POST(fb->buf, fb->len);
  
  if (httpResponseCode > 0) {
    String response = http.getString();
    Serial.println("Image uploaded successfully");
    showMessage("Camera", "Upload success!");
    
    // Send metadata via MQTT
    DynamicJsonDocument doc(200);
    doc["device_id"] = DEVICE_ID;
    doc["image_id"] = imageCount;
    doc["size"] = fb->len;
    doc["timestamp"] = millis();
    
    String jsonString;
    serializeJson(doc, jsonString);
    
    client.publish("health/image_metadata", jsonString.c_str());
    setAssistantState(HAPPY);
  } else {
    Serial.print("Error on sending POST: ");
    Serial.println(httpResponseCode);
    showMessage("Camera", "Upload failed!");
    setAssistantState(ALERT);
  }
  
  http.end();
}

// Modify the captureAndSendImage function
void captureAndSendImage() {
  setAssistantState(THINKING);
  showMessage("Camera", "Taking photo...");
  
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Camera capture failed");
    showMessage("Camera", "Capture failed!");
    setAssistantState(ALERT);
    return;
  }

  uploadImageHTTP(fb);
  imageCount++;

  esp_camera_fb_return(fb);
  setAssistantState(NORMAL);
}

void writeFile(fs::FS &fs, const char * path, uint8_t * data, size_t len) {
  Serial.printf("Writing file: %s\r\n", path);
  showMessage("Storage", "Writing file...");
  
  File file = fs.open(path, FILE_WRITE);
  if(!file) {
    Serial.println("Failed to open file for writing");
    showMessage("Storage", "File open failed!");
    setAssistantState(ALERT);
    return;
  }
  if(file.write(data, len) == len) {
    Serial.println("File written");
    showMessage("Storage", "File written!");
    setAssistantState(HAPPY);
  } else {
    Serial.println("Write failed");
    showMessage("Storage", "Write failed!");
    setAssistantState(ALERT);
  }
  file.close();
}

bool reconnectSensor() {
  Serial.println("Attempting sensor reconnection...");
  setAssistantState(THINKING);
  showMessage("Sensor", "Reconnecting...");
  
  // Reset I2C bus
  Wire.end();
  delay(100);
  Wire.begin(SDA_PIN, SCL_PIN);
  
  // Try 3 times
  for (int i = 0; i < 3; i++) {
    if (pox.begin()) {
      showMessage("Sensor", "Reconnected!");
      setAssistantState(HAPPY);
      pox.setIRLedCurrent(MAX30100_LED_CURR_7_6MA);
      pox.setOnBeatDetectedCallback(onBeatDetected);
      return true;
    }
    delay(1000);
  }
  
  showMessage("Sensor", "Reconnect failed");
  setAssistantState(ALERT);
  return false;
}

void checkWiFiConnection() {
  if (WiFi.status() != WL_CONNECTED) {
    setAssistantState(ALERT);
    showMessage("WiFi", "Disconnected!");
    
    WiFi.disconnect();
    WiFi.begin(ssid, password);
    
    // Try for 10 seconds to reconnect
    unsigned long startAttemptTime = millis();
    while (WiFi.status() != WL_CONNECTED && 
           millis() - startAttemptTime < 10000) {
      delay(500);
      setAssistantState(THINKING);
    }
    
    if (WiFi.status() == WL_CONNECTED) {
      showMessage("WiFi", "Reconnected!");
      setAssistantState(HAPPY);
    }
  }
}

void checkDisplay() {
  if (millis() - lastActivityTime > SCREEN_TIMEOUT) {
    // Dim or turn off display to save power
    u8g2.setPowerSave(1); // Turn off display
  } else {
    u8g2.setPowerSave(0); // Ensure display is on
  }
}

// *** UPDATED AUDIO FUNCTIONS BELOW ***

void setupI2S() {
  Serial.println("Setting up I2S for XIAO ESP32S3 Sense microphone...");
  setAssistantState(THINKING);
  showMessage("Audio", "Setting up...");
  
  // Set up the pins used for PDM audio input
  i2s.setPinsPdmRx(I2S_WS, I2S_SD);  // WS=42 (LRCK), SD=41 (DATA)
  
  // Start I2S at 16 kHz with 16-bits per sample in PDM mono mode
  if (!i2s.begin(I2S_MODE_PDM_RX, AUDIO_SAMPLE_RATE, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO)) {
    Serial.println("Failed to initialize I2S!");
    showMessage("Audio", "Init failed!");
    setAssistantState(ALERT);
    return;
  }
  
  Serial.println("I2S microphone initialized successfully");
  showMessage("Audio", "Ready!");
  setAssistantState(HAPPY);
}

// Function to handle SOS button press
void checkSOSButton() {
  // Read button state (assuming active LOW button)
  int buttonState = digitalRead(SOS_BUTTON_PIN);
  
  // Check if button is pressed (LOW) and debounce
  if (buttonState == LOW && (millis() - lastButtonTime > DEBOUNCE_TIME)) {
    lastButtonTime = millis();
    
    Serial.println("SOS Button Pressed!");
    setAssistantState(ALERT);
    showMessage("ALERT", "SOS ACTIVATED!");
    
    // Capture image immediately
    captureAndSendImage();
    
    // Send SOS alert
    sendSOSAlert("SOS_BUTTON");
    
    // Reset activity time to keep display on
    lastActivityTime = millis();
  }
}

// Function to send SOS alert via MQTT
void sendSOSAlert(String triggerSource) {
  // Get current health data
  float heartRate = pox.getHeartRate();
  float spO2 = pox.getSpO2();
  
  setAssistantState(ALERT);
  showMessage("ALERT", "Sending SOS!");
  
  // Create JSON document
  DynamicJsonDocument doc(512);
  doc["device_id"] = DEVICE_ID;
  doc["alert_type"] = "SOS";
  doc["trigger"] = triggerSource;
  doc["heart_rate"] = heartRate;
  doc["spo2"] = spO2;
  doc["timestamp"] = millis();
  
  // Serialize JSON to string
  String jsonString;
  serializeJson(doc, jsonString);
  
  // Send alert via MQTT
  client.publish("health/alerts", jsonString.c_str());
  
  Serial.println("SOS Alert sent: " + jsonString);
  showMessage("ALERT", "SOS sent!");
}

// Function to check if there's an anomaly in health parameters
void checkHealthParameters() {
  float heartRate = pox.getHeartRate();
  float spO2 = pox.getSpO2();
  
  // Send the health data with device ID for processing by ML models
  DynamicJsonDocument doc(256);
  doc["device_id"] = DEVICE_ID;
  doc["heart_rate"] = heartRate;
  doc["spo2"] = spO2;
  doc["timestamp"] = millis();
  
  String jsonString;
  serializeJson(doc, jsonString);
  
  // Send to a different topic for ML processing
  client.publish("health/parameters", jsonString.c_str());
}

// Updated function to record audio using XIAO ESP32S3 Sense microphone
void recordAndProcessAudio() {
  if (audioProcessingActive) {
    return; // Already recording
  }
  
  audioProcessingActive = true;
  
  Serial.println("Recording audio with XIAO ESP32S3 Sense microphone...");
  setAssistantState(RECORDING);
  showMessage("Audio", "Recording...");
  
  // Create filename for the audio recording
  String filename = "/AUDIO_" + String(audioFileCounter++) + ".wav";
  Serial.print("Recording to ");
  Serial.println(filename);
  infoMessage = filename;
  
  // Record audio data for the specified duration
  uint8_t *wav_buffer;
  size_t wav_size;
  
  // Record audio using the I2S library's WAV recording function
  wav_buffer = i2s.recordWAV(AUDIO_RECORD_DURATION, &wav_size);
  
  if (!wav_buffer) {
    Serial.println("Failed to record audio!");
    showMessage("Audio", "Record failed!");
    setAssistantState(ALERT);
    audioProcessingActive = false;
    return;
  }
  
  Serial.print("Recording complete. Size: ");
  Serial.print(wav_size);
  Serial.println(" bytes");
  showMessage("Audio", "Recording done!");
  
  // Save the recorded audio to SD card
  setAssistantState(THINKING);
  showMessage("Audio", "Saving to SD...");
  
  File file = SD.open(filename.c_str(), FILE_WRITE);
  if (!file) {
    Serial.println("Failed to open file for writing!");
    showMessage("Audio", "Save failed!");
    setAssistantState(ALERT);
    free(wav_buffer);
    audioProcessingActive = false;
    return;
  }
  
  // Write the WAV data to the file
  if (file.write(wav_buffer, wav_size) != wav_size) {
    Serial.println("Failed to write complete audio data to file!");
    showMessage("Audio", "Write incomplete!");
    setAssistantState(ALERT);
  } else {
    Serial.print("Successfully saved to ");
    Serial.println(filename);
    showMessage("Audio", "Saved: " + filename);
    setAssistantState(HAPPY);
  }
  
  // Close the file
  file.close();
  
  // Process the audio data if needed
  showMessage("Audio", "Processing...");
  setAssistantState(THINKING);
  processAudioForKeywords(wav_buffer, wav_size, filename);
  
  // Free the audio buffer
  free(wav_buffer);
  
  audioProcessingActive = false;
  setAssistantState(NORMAL);
}

// Function to process audio for keywords
void processAudioForKeywords(uint8_t* audioData, size_t dataSize, String filename) {
  // Prepare and send audio data via HTTP for keyword processing
  HTTPClient http;
  http.begin("http://192.168.58.116:5000/process_audio");
  http.addHeader("Content-Type", "application/octet-stream");
  http.addHeader("Device-ID", DEVICE_ID);
  http.addHeader("Filename", filename);
  
  int httpCode = http.POST(audioData, dataSize);
  
  if (httpCode > 0) {
    String response = http.getString();
    Serial.println("Audio processing response: " + response);
    
    // Parse JSON response
    DynamicJsonDocument doc(512);
    DeserializationError error = deserializeJson(doc, response);
    
    if (!error) {
      bool keyword_detected = doc["keyword_detected"];
      
      if (keyword_detected) {
        String keyword = doc["keyword"];
        detectedKeyword = keyword;
        keywordDetected = true;
        
        showMessage("Audio", "Keyword: " + keyword);
        setAssistantState(HAPPY);
        
        // If "help" or "ouch" is detected, capture an image immediately
        if (keyword == "help" || keyword == "ouch") {
          captureAndSendImage();
          
          // Send SOS alert with the detected keyword
          sendSOSAlert(keyword);
        }
      } else {
        showMessage("Audio", "No keywords");
      }
    }
  } else {
    Serial.println("Audio HTTP Error: " + String(httpCode));
    showMessage("Audio", "Process error");
    setAssistantState(ALERT);
  }
  
  http.end();
}

// Assistant display functions
void setAssistantState(AssistantState state) {
  currentState = state;
  animationFrame = 0;
  lastAnimationTime = millis();
  lastActivityTime = millis(); // Reset screen timeout
}

void showMessage(String status, String info) {
  statusMessage = status;
  infoMessage = info;
  messageDisplayTime = millis();
  lastActivityTime = millis(); // Reset screen timeout
}

// Draw the assistant character based on current state and animation frame
void drawAssistant() {
  int centerX = 32;
  int centerY = 40;
  int eyeSize = 5;
  int mouthWidth = 20;
  
  // Draw body (circle)
  u8g2.drawCircle(centerX, centerY, 25);
  
  // Draw eyes based on state
  switch(currentState) {
    case NORMAL:
      // Normal eyes
      u8g2.drawDisc(centerX - 10, centerY - 5, eyeSize);
      u8g2.drawDisc(centerX + 10, centerY - 5, eyeSize);
      
      // Normal smile
      u8g2.drawLine(centerX - mouthWidth/2, centerY + 10, centerX + mouthWidth/2, centerY + 10);
      break;
      
    case HAPPY:
      // Happy eyes
      u8g2.drawDisc(centerX - 10, centerY - 5, eyeSize);
      u8g2.drawDisc(centerX + 10, centerY - 5, eyeSize);
      
      // Smile
      u8g2.drawLine(centerX - mouthWidth/2, centerY + 10, centerX, centerY + 15);
      u8g2.drawLine(centerX, centerY + 15, centerX + mouthWidth/2, centerY + 10);
      break;
      
    case THINKING:
      // Thinking eyes (slightly closed)
      u8g2.drawEllipse(centerX - 10, centerY - 5, eyeSize, eyeSize - 2);
      u8g2.drawEllipse(centerX + 10, centerY - 5, eyeSize, eyeSize - 2);
      
      // Thinking mouth
      u8g2.drawLine(centerX - mouthWidth/3, centerY + 10, centerX + mouthWidth/3, centerY + 10);
      break;
      
    case ALERT:
      // Alert eyes (wide open)
      u8g2.drawCircle(centerX - 10, centerY - 5, eyeSize + 1);
      u8g2.drawCircle(centerX + 10, centerY - 5, eyeSize + 1);
      u8g2.drawDisc(centerX - 10, centerY - 5, eyeSize - 1);
      u8g2.drawDisc(centerX + 10, centerY - 5, eyeSize - 1);
      
      // Alert mouth (circular)
      u8g2.drawCircle(centerX, centerY + 10, 7);
      break;
      
    case RECORDING:
      // Recording eyes (blinking)
      if (animationFrame % 2 == 0) {
        u8g2.drawDisc(centerX - 10, centerY - 5, eyeSize);
        u8g2.drawDisc(centerX + 10, centerY - 5, eyeSize);
      } else {
        u8g2.drawLine(centerX - 10 - eyeSize + 1, centerY - 5, centerX - 10 + eyeSize - 1, centerY - 5);
        u8g2.drawLine(centerX + 10 - eyeSize + 1, centerY - 5, centerX + 10 + eyeSize - 1, centerY - 5);
      }
      
      // Recording mouth (circle for microphone)
      u8g2.drawCircle(centerX, centerY + 10, 5);
      u8g2.drawCircle(centerX, centerY + 10, 3);
      break;
      
    case LOADING:
      // Loading eyes
      u8g2.drawDisc(centerX - 10, centerY - 5, eyeSize);
      u8g2.drawDisc(centerX + 10, centerY - 5, eyeSize);
      
      // Loading animation mouth
      int loadPos = animationFrame % 3;
      u8g2.drawDisc(centerX - 7 + (loadPos * 7), centerY + 10, 3);
      break;
  }
  
  // Draw animated elements based on state and frame
  switch(currentState) {
    case THINKING:{
      // Draw thinking bubbles
      int bubblePos = animationFrame % 3;
      u8g2.drawCircle(centerX + 20 + bubblePos * 3, centerY - 15 - bubblePos * 3, 2 + bubblePos);
      break;
    }
    case LOADING:{
      // Loading spinner
      int x = centerX + 30;
      int y = centerY;
      int radius = 8;
      float angle = (animationFrame % 8) * 0.25 * PI;
      int px = x + radius * cos(angle);
      int py = y + radius * sin(angle);
      u8g2.drawLine(x, y, px, py);
      u8g2.drawDisc(px, py, 2);
      break;
    }
  }
}

// Update display with assistant and status information
void updateAssistantDisplay() {
  u8g2.clearBuffer();
  
  // Draw the assistant on the left side
  drawAssistant();
  
  // Draw status information on the right side
  u8g2.setFont(u8g2_font_6x10_tf);
  
  // Draw the status messages
  if (millis() - messageDisplayTime < MESSAGE_DISPLAY_DURATION) {
    u8g2.drawBox(65, 0, 63, 11);
    u8g2.setDrawColor(0);
    u8g2.drawStr(67, 9, statusMessage.c_str());
    u8g2.setDrawColor(1);
    u8g2.drawStr(67, 23, infoMessage.c_str());
  }
  
  // Draw health data
  float heartRate = pox.getHeartRate();
  float spO2 = pox.getSpO2();
  
  u8g2.drawStr(67, 40, "HR:");
  if (heartRate > 0) {
    u8g2.setCursor(90, 40);
    u8g2.print(heartRate, 0);
    u8g2.drawStr(115, 40, "bpm");
    
    // Draw little heart that blinks with detected beats
    u8g2.drawLine(81, 40, 85, 36);
    u8g2.drawLine(85, 36, 89, 40);
    u8g2.drawLine(89, 40, 85, 44);
    u8g2.drawLine(85, 44, 81, 40);
  } else {
    u8g2.drawStr(90, 40, "---");
  }
  
  u8g2.drawStr(67, 55, "SpO2:");
  if (spO2 > 0) {
    u8g2.setCursor(100, 55);
    u8g2.print(spO2, 0);
    u8g2.drawStr(115, 55, "%");
  } else {
    u8g2.drawStr(100, 55, "---");
  }
  
  // Draw connection status icons
  if (WiFi.status() == WL_CONNECTED) {
    // Draw WiFi icon
    for (int i = 0; i < 3; i++) {
      u8g2.drawCircle(75, 75, 5 + (i * 5));
    }
  } else {
    u8g2.drawLine(70, 70, 80, 80);
    u8g2.drawLine(70, 80, 80, 70);
  }
  
  if (client.connected()) {
    // Draw MQTT icon
    u8g2.drawBox(90, 70, 10, 10);
    u8g2.drawLine(95, 70, 95, 65);
    u8g2.drawLine(90, 65, 100, 65);
  } else {
    u8g2.drawFrame(90, 70, 10, 10);
    u8g2.drawLine(90, 70, 100, 80);
  }
  
  if (camera_sign) {
    // Draw camera icon
    u8g2.drawRFrame(108, 70, 15, 10, 2);
    u8g2.drawCircle(115, 75, 3);
  }
  
  // Draw device ID and version at bottom
  u8g2.setFont(u8g2_font_4x6_tf);
  u8g2.drawStr(5, 90, "ID:");
  u8g2.drawStr(20, 90, DEVICE_ID);
  u8g2.drawStr(90, 90, "v1.0");
  
  u8g2.sendBuffer();
}

void setup() {
  Serial.begin(115200);
  
  Wire.begin(SDA_PIN, SCL_PIN);
  
  u8g2.begin();
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_ncenB08_tr);
  
  setAssistantState(THINKING);
  showMessage("System", "Initializing...");
  updateAssistantDisplay();

  // Initialize SOS button pin
  pinMode(SOS_BUTTON_PIN, INPUT_PULLUP);

  showMessage("WiFi", "Connecting...");
  updateAssistantDisplay();
  
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    animationFrame = (animationFrame + 1) % 4;
    updateAssistantDisplay();
  }
  Serial.println("WiFi connected");
  showMessage("WiFi", "Connected!");
  setAssistantState(HAPPY);
  updateAssistantDisplay();
  delay(1000);

  client.setServer(mqttServer, mqttPort);
  client.setCallback(callback);

  showMessage("MQTT", "Connecting...");
  setAssistantState(THINKING);
  updateAssistantDisplay();

  unsigned long mqttStartTime = millis();
  while (!client.connected()) {
    Serial.println("Connecting to MQTT...");
    if (client.connect("ESP32Client", mqttUser, mqttPassword)) {
      Serial.println("MQTT connected");
      client.subscribe("health/commands");
      showMessage("MQTT", "Connected!");
      setAssistantState(HAPPY);
    } else {
      Serial.print("Failed with state ");
      Serial.println(client.state());
      showMessage("MQTT", "Connection failed!");
      setAssistantState(ALERT);
      delay(2000);
      
      // Timeout after 10 seconds
      if (millis() - mqttStartTime > 10000) {
        Serial.println("MQTT connection timeout");
        showMessage("MQTT", "Timeout, continuing...");
        break;
      }
    }
  }
  updateAssistantDisplay();
  delay(1000);
  
  // Initialize Pulse Oximeter
  showMessage("Sensor", "Initializing...");
  setAssistantState(THINKING);
  updateAssistantDisplay();
  
  if (!pox.begin()) {
    Serial.println("FAILED: Pulse Oximeter not found");
    showMessage("Sensor", "Not found!");
    setAssistantState(ALERT);
  } else {
    Serial.println("Pulse Oximeter initialized");
    showMessage("Sensor", "Ready!");
    setAssistantState(HAPPY);
    
    pox.setIRLedCurrent(MAX30100_LED_CURR_7_6MA);
    pox.setOnBeatDetectedCallback(onBeatDetected);
  }
  updateAssistantDisplay();
  delay(1000);
  
  // Initialize SD Card
  showMessage("Storage", "Initializing...");
  setAssistantState(THINKING);
  updateAssistantDisplay();
  
  if (!SD.begin()) {
    Serial.println("SD Card initialization failed!");
    showMessage("Storage", "Failed!");
    setAssistantState(ALERT);
  } else {
    Serial.println("SD Card initialized.");
    sd_sign = true;
    showMessage("Storage", "Ready!");
    setAssistantState(HAPPY);
    
    uint8_t cardType = SD.cardType();
    uint64_t cardSize = SD.cardSize() / (1024 * 1024);
    Serial.printf("SD Card Type: %d Size: %lluMB\n", cardType, cardSize);
  }
  updateAssistantDisplay();
  delay(1000);
  
  // Initialize Camera
  setupCamera();
  updateAssistantDisplay();
  delay(1000);
  
  // Initialize I2S for microphone
  setupI2S();
  updateAssistantDisplay();
  delay(1000);
  
  showMessage("System", "Ready!");
  setAssistantState(NORMAL);
  updateAssistantDisplay();
  
  // Set initial time references
  lastCaptureTime = millis();
  lastAudioCaptureTime = millis();
  lastActivityTime = millis();
  lastAnimationTime = millis();
}

void loop() {
  // Update animation frame if needed
  if (millis() - lastAnimationTime > ANIMATION_INTERVAL) {
    animationFrame++;
    lastAnimationTime = millis();
    updateAssistantDisplay();
  }
  
  // Check power management for display
  checkDisplay();
  
  // Check SOS button
  checkSOSButton();
  
  // Maintain MQTT connection
  if (!client.connected()) {
    reconnectMQTT();
  }
  client.loop();
  
  // Maintain WiFi connection
  checkWiFiConnection();
  
  // Update MAX30100 sensor readings
  pox.update();
  
  // Report health parameters periodically
  if (millis() - tsLastReport > REPORTING_PERIOD_MS) {
    float heartRate = pox.getHeartRate();
    float spO2 = pox.getSpO2();
    
    // Only publish if we have valid readings
    if (heartRate > 0 && spO2 > 0) {
      Serial.print("Heart rate: ");
      Serial.print(heartRate);
      Serial.print(" bpm / SpO2: ");
      Serial.print(spO2);
      Serial.println(" %");
      
      // Publish heart rate and SpO2 to MQTT
      char msg[100];
      sprintf(msg, "{\"device_id\":\"%s\",\"heart_rate\":%.1f,\"spo2\":%.1f}", DEVICE_ID, heartRate, spO2);
      client.publish("health/vitals", msg);
      
      // Check health parameters for anomalies
      checkHealthParameters();
      
      // Update the display with new data
      updateAssistantDisplay();
    } else {
      Serial.println("Waiting for valid readings...");
      
      // Try to reconnect the sensor if we're not getting readings
      static unsigned long lastReconnectAttempt = 0;
      if (millis() - lastReconnectAttempt > 30000) { // Try every 30 seconds
        reconnectSensor();
        lastReconnectAttempt = millis();
      }
      
    }
    
    tsLastReport = millis();
  }
  
  // Capture and send image periodically
  if (camera_sign && millis() - lastCaptureTime > IMAGE_CAPTURE_INTERVAL) {
    captureAndSendImage();
    lastCaptureTime = millis();
  }
  
  // Record audio periodically
  if (millis() - lastAudioCaptureTime > AUDIO_CAPTURE_INTERVAL && !audioProcessingActive) {
    recordAndProcessAudio();
    lastAudioCaptureTime = millis();
  }
  
  // Process any detected keywords
  if (keywordDetected) {
    Serial.println("Processing detected keyword: " + detectedKeyword);
    keywordDetected = false;
    
    // Reset for next detection
    detectedKeyword = "";
  }
  
  // Minimal delay to prevent hogging the CPU
  delay(10);
}
