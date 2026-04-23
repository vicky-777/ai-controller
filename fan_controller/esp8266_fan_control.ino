/*
  ============================================================
  DC Toy Fan Controller — ESP8266
  ============================================================
  Hardware:
    - ESP8266 (NodeMCU / Wemos D1 Mini)
    - L298N or L9110 motor driver
    - DC toy fan
    - DHT22 temperature + humidity sensor (optional)

  Wiring (L298N):
    ESP8266 D1 (GPIO5)  →  L298N ENA     (PWM speed signal)
    ESP8266 D2 (GPIO4)  →  L298N IN1     (direction, always HIGH)
    ESP8266 D3 (GPIO0)  →  L298N IN2     (direction, always LOW)
    ESP8266 GND         →  L298N GND
    External 5–12V      →  L298N VCC
    L298N OUT1 & OUT2   →  Fan motor terminals

  Wiring (DHT22 — optional):
    DHT22 VCC  →  ESP8266 3.3V
    DHT22 GND  →  ESP8266 GND
    DHT22 DATA →  ESP8266 D4 (GPIO2)

  Libraries needed (install via Arduino Library Manager):
    - PubSubClient  by Nick O'Leary
    - ArduinoJson   by Benoit Blanchon
    - DHT sensor    by Adafruit  (only if using DHT22)
    - ESP8266WiFi   (comes with ESP8266 board package)

  Board setup in Arduino IDE:
    Board: NodeMCU 1.0 (ESP-12E Module)  or  LOLIN(Wemos) D1 Mini
    Upload Speed: 115200
    Port: your COM port
  ============================================================
*/

#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
// Uncomment below if you have a DHT22 sensor connected
// #include <DHT.h>

// ── WiFi credentials ─────────────────────────────────────
const char* WIFI_SSID     = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// ── MQTT broker settings ──────────────────────────────────
// Free broker — no account needed for testing
const char* MQTT_BROKER   = "broker.hivemq.com";
const int   MQTT_PORT     = 1883;
const char* MQTT_TOPIC    = "home/fan/set";       // subscribe (receive commands)
const char* MQTT_STATUS   = "home/fan/status";   // publish   (send current state back)
// Give your device a unique ID to avoid conflicts on public broker
const char* MQTT_CLIENT_ID = "esp8266_fan_001";

// ── ThingSpeak settings ───────────────────────────────────
const char* TS_API_KEY    = "04O2PW7EKU2BZSWF;
const char* TS_URL        = "http://api.thingspeak.com/update";
// ThingSpeak fields:
//   field1 = fan speed level (0=off, 1=low, 2=medium, 3=high)
//   field2 = temperature °C  (if DHT22 connected)
//   field3 = humidity %      (if DHT22 connected)
const unsigned long TS_INTERVAL = 15000; // send to ThingSpeak every 15 seconds

// ── Pin definitions ───────────────────────────────────────
const int PIN_ENA  = D1;  // GPIO5 — PWM speed to motor driver ENA
const int PIN_IN1  = D2;  // GPIO4 — motor direction IN1 (keep HIGH)
const int PIN_IN2  = D3;  // GPIO0 — motor direction IN2 (keep LOW)
// const int PIN_DHT  = D4;  // GPIO2 — DHT22 data pin (uncomment if using)

// ── PWM duty cycle values for each speed level ───────────
//    ESP8266 analogWrite range: 0–1023
const int PWM_OFF    = 0;    // 0%   — fan stopped
const int PWM_LOW    = 307;  // 30%  — gentle breeze
const int PWM_MEDIUM = 665;  // 65%  — moderate
const int PWM_HIGH   = 1023; // 100% — full speed

// ── DHT22 sensor (uncomment if using) ────────────────────
// #define DHTTYPE DHT22
// DHT dht(PIN_DHT, DHTTYPE);

// ── Global state ──────────────────────────────────────────
WiFiClient   wifiClient;
PubSubClient mqttClient(wifiClient);

String  currentSpeedLevel = "off";  // tracks current fan level
int     currentPWM        = 0;      // tracks current PWM value
unsigned long lastThingSpeakTime = 0;

// ─────────────────────────────────────────────────────────
// Connect to WiFi
// ─────────────────────────────────────────────────────────
void connectWiFi() {
  Serial.print("Connecting to WiFi: ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    attempts++;
    if (attempts > 40) {
      Serial.println("\nWiFi failed! Restarting...");
      ESP.restart();
    }
  }

  Serial.println("\nWiFi connected!");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
}

// ─────────────────────────────────────────────────────────
// Set fan speed based on level string
// ─────────────────────────────────────────────────────────
void setFanSpeed(String level) {
  level.toLowerCase();
  level.trim();

  int pwmValue = 0;

  if (level == "off") {
    pwmValue = PWM_OFF;
  } else if (level == "low") {
    pwmValue = PWM_LOW;
  } else if (level == "medium") {
    pwmValue = PWM_MEDIUM;
  } else if (level == "high") {
    pwmValue = PWM_HIGH;
  } else {
    Serial.print("Unknown speed level received: ");
    Serial.println(level);
    return; // ignore unknown values
  }

  // Apply PWM to motor driver ENA pin
  analogWrite(PIN_ENA, pwmValue);

  currentSpeedLevel = level;
  currentPWM        = pwmValue;

  Serial.print("Fan set to: ");
  Serial.print(level);
  Serial.print("  (PWM=");
  Serial.print(pwmValue);
  Serial.println(")");

  // Publish status back to MQTT so the web UI can update
  String statusMsg = "{\"speed\":\"" + level + "\",\"pwm\":" + String(pwmValue) + "}";
  mqttClient.publish(MQTT_STATUS, statusMsg.c_str(), true); // retained=true
}

// ─────────────────────────────────────────────────────────
// MQTT message received callback
// ─────────────────────────────────────────────────────────
void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  // Convert payload bytes to string
  String message = "";
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }

  Serial.print("MQTT received on [");
  Serial.print(topic);
  Serial.print("]: ");
  Serial.println(message);

  // Parse JSON: expected format {"speed": "high"}
  StaticJsonDocument<128> doc;
  DeserializationError error = deserializeJson(doc, message);

  if (error) {
    Serial.print("JSON parse error: ");
    Serial.println(error.c_str());
    return;
  }

  if (doc.containsKey("speed")) {
    String speed = doc["speed"].as<String>();
    setFanSpeed(speed);
  } else {
    Serial.println("JSON missing 'speed' key");
  }
}

// ─────────────────────────────────────────────────────────
// Connect to MQTT broker
// ─────────────────────────────────────────────────────────
void connectMQTT() {
  while (!mqttClient.connected()) {
    Serial.print("Connecting to MQTT broker...");

    if (mqttClient.connect(MQTT_CLIENT_ID)) {
      Serial.println("connected!");
      mqttClient.subscribe(MQTT_TOPIC);
      Serial.print("Subscribed to: ");
      Serial.println(MQTT_TOPIC);

      // Announce online
      mqttClient.publish(MQTT_STATUS, "{\"status\":\"online\",\"speed\":\"off\"}", true);
    } else {
      Serial.print("failed, rc=");
      Serial.print(mqttClient.state());
      Serial.println(" — retrying in 3 seconds");
      delay(3000);
    }
  }
}

// ─────────────────────────────────────────────────────────
// Send data to ThingSpeak
// ─────────────────────────────────────────────────────────
void sendToThingSpeak() {
  if (WiFi.status() != WL_CONNECTED) return;

  // Map speed level to numeric value for graphing
  int speedNum = 0;
  if      (currentSpeedLevel == "low")    speedNum = 1;
  else if (currentSpeedLevel == "medium") speedNum = 2;
  else if (currentSpeedLevel == "high")   speedNum = 3;

  // Read sensor if DHT22 is connected
  // float temperature = dht.readTemperature();
  // float humidity    = dht.readHumidity();

  // Build ThingSpeak URL
  String url = String(TS_URL) +
               "?api_key=" + TS_API_KEY +
               "&field1="  + String(speedNum);
               // + "&field2=" + String(temperature)   // uncomment if DHT22
               // + "&field3=" + String(humidity);      // uncomment if DHT22

  WiFiClient client;
  HTTPClient http;
  http.begin(client, url);

  int httpCode = http.GET();

  if (httpCode == 200) {
    Serial.println("ThingSpeak updated OK");
  } else {
    Serial.print("ThingSpeak error: ");
    Serial.println(httpCode);
  }

  http.end();
}

// ─────────────────────────────────────────────────────────
// SETUP
// ─────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  Serial.println("\n\n=== DC Fan Controller — ESP8266 ===");

  // Motor driver direction pins — set once, never change
  pinMode(PIN_IN1, OUTPUT);
  pinMode(PIN_IN2, OUTPUT);
  digitalWrite(PIN_IN1, HIGH); // forward direction
  digitalWrite(PIN_IN2, LOW);

  // ENA pin — PWM output
  pinMode(PIN_ENA, OUTPUT);
  analogWrite(PIN_ENA, PWM_OFF); // start with fan off

  // Set PWM frequency — 1000 Hz is smooth for DC motors
  analogWriteFreq(1000);
  analogWriteRange(1023); // 10-bit range

  // DHT22 init (uncomment if using)
  // dht.begin();

  connectWiFi();

  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setCallback(onMqttMessage);

  connectMQTT();

  Serial.println("=== Setup complete. Waiting for commands... ===\n");
}

// ─────────────────────────────────────────────────────────
// LOOP
// ─────────────────────────────────────────────────────────
void loop() {
  // Reconnect WiFi if dropped
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi lost — reconnecting...");
    connectWiFi();
  }

  // Reconnect MQTT if dropped
  if (!mqttClient.connected()) {
    connectMQTT();
  }

  // Process incoming MQTT messages
  mqttClient.loop();

  // Send to ThingSpeak every 15 seconds
  unsigned long now = millis();
  if (now - lastThingSpeakTime >= TS_INTERVAL) {
    lastThingSpeakTime = now;
    sendToThingSpeak();
  }
}
